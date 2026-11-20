"""Persistent search cache backed by SQLite.

Search results are stored per query with an expiry time, so changing page,
sort or filters doesn't download everything from the stores again, and the
cache survives an application restart. Expired rows are deleted whenever new
results are saved and when the cache is opened.
"""
import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from scrapers.base import Product


class SearchCache:
    def __init__(self, path, clock=time.time):
        self.path = Path(path)
        self.clock = clock  # injectable so tests can move time forward
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS searches ("
                " query TEXT PRIMARY KEY,"
                " expires_at REAL NOT NULL,"
                " results TEXT NOT NULL)"
            )
        self.purge_expired()

    @contextmanager
    def _connect(self):
        # A short-lived connection per call keeps this safe to use from
        # several request threads at once. It is committed and closed on
        # exit, so no file handle is left open.
        con = sqlite3.connect(self.path, timeout=10)
        try:
            with con:
                yield con
        finally:
            con.close()

    def get(self, query):
        """Cached results for `query`, or None if missing or expired.

        Results are a list of (store, products, error) tuples, the same
        shape the scrapers produce.
        """
        with self._connect() as db:
            row = db.execute(
                "SELECT expires_at, results FROM searches WHERE query = ?",
                (query,),
            ).fetchone()
        if row is None or row[0] <= self.clock():
            return None
        return [
            (r["store"], [Product(**p) for p in r["products"]], r["error"])
            for r in json.loads(row[1])
        ]

    def set(self, query, results, ttl):
        """Store results for `ttl` seconds and drop anything already expired."""
        payload = json.dumps([
            {"store": store, "products": [asdict(p) for p in products], "error": error}
            for store, products, error in results
        ])
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO searches (query, expires_at, results)"
                " VALUES (?, ?, ?)",
                (query, self.clock() + ttl, payload),
            )
        self.purge_expired()

    def purge_expired(self):
        """Delete expired entries. Returns how many rows were removed."""
        with self._connect() as db:
            cur = db.execute(
                "DELETE FROM searches WHERE expires_at <= ?", (self.clock(),)
            )
            return cur.rowcount

    def __len__(self):
        with self._connect() as db:
            return db.execute("SELECT COUNT(*) FROM searches").fetchone()[0]
