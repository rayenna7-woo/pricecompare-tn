"""The SQLite search cache."""
from cache import SearchCache
from conftest import make_product


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


def sample_results():
    return [
        ("TunisiaNet", [make_product(price=1500), make_product(price=1600)], None),
        ("SpaceNet", [], "blocked by the site (403)"),
    ]


def test_round_trip_keeps_products_and_errors(tmp_path):
    cache = SearchCache(tmp_path / "c.sqlite3", clock=Clock())
    cache.set("rtx 5060", sample_results(), ttl=600)
    assert cache.get("rtx 5060") == sample_results()


def test_survives_a_restart(tmp_path):
    path = tmp_path / "c.sqlite3"
    clock = Clock()
    SearchCache(path, clock=clock).set("rtx 5060", sample_results(), ttl=600)
    reopened = SearchCache(path, clock=clock)  # e.g. after the app restarts
    assert reopened.get("rtx 5060") == sample_results()


def test_expired_entries_are_not_returned(tmp_path):
    clock = Clock()
    cache = SearchCache(tmp_path / "c.sqlite3", clock=clock)
    cache.set("rtx 5060", sample_results(), ttl=600)
    clock.now += 601
    assert cache.get("rtx 5060") is None


def test_expired_entries_are_deleted(tmp_path):
    clock = Clock()
    cache = SearchCache(tmp_path / "c.sqlite3", clock=clock)
    cache.set("old", sample_results(), ttl=60)
    cache.set("fresh", sample_results(), ttl=600)
    clock.now += 120
    assert cache.purge_expired() == 1
    assert len(cache) == 1


def test_saving_new_results_cleans_up_expired_ones(tmp_path):
    clock = Clock()
    cache = SearchCache(tmp_path / "c.sqlite3", clock=clock)
    cache.set("old", sample_results(), ttl=60)
    clock.now += 120
    cache.set("new", sample_results(), ttl=600)
    assert len(cache) == 1


def test_opening_the_cache_cleans_up_expired_ones(tmp_path):
    path = tmp_path / "c.sqlite3"
    clock = Clock()
    SearchCache(path, clock=clock).set("old", sample_results(), ttl=60)
    clock.now += 120
    assert len(SearchCache(path, clock=clock)) == 0


def test_missing_query_returns_none(tmp_path):
    assert SearchCache(tmp_path / "c.sqlite3").get("nothing") is None
