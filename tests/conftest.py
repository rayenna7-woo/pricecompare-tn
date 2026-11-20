import types

import pytest

from app import create_app
from scrapers.base import Product, ScraperError


def make_product(store="TunisiaNet", name="Carte graphique RTX 5060", price=1000.0,
                 status="in", url=None):
    return Product(
        store=store,
        name=name,
        price=price,
        price_text=f"{price:,.3f} DT".replace(",", " "),
        status=status,
        stock_text={"in": "En stock", "order": "Sur commande", "out": "Hors stock"}[status],
        url=url or f"https://example.com/{store}/{name}/{price}",
        image=None,
    )


class FakeScraper:
    """Stands in for a store module: has STORE and search(query)."""

    def __init__(self, store, products=(), error=None):
        self.STORE = store
        self.products = list(products)
        self.error = error
        self.calls = 0

    def search(self, query):
        self.calls += 1
        if self.error:
            raise self.error
        return list(self.products)


@pytest.fixture
def make_client(tmp_path):
    """Build a test client for an app that uses the given fake scrapers."""
    def factory(*scrapers):
        app = create_app({
            "TESTING": True,
            "SCRAPERS": list(scrapers),
            "CACHE_PATH": str(tmp_path / "cache.sqlite3"),
        })
        return app.test_client()
    return factory


@pytest.fixture
def blocked():
    return ScraperError("this store blocks automated access (Cloudflare bot check)")


__all__ = ["FakeScraper", "make_product", "types"]
