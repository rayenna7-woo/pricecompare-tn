"""Routes, rendering, caching and store failures, with fake scrapers."""
import app as app_module
from app import create_app
from conftest import FakeScraper, make_product


def rtx(n, store="TunisiaNet", start=1000, status="in"):
    return [make_product(store=store, name=f"Carte RTX 5060 n{i}", price=start + i, status=status)
            for i in range(n)]


def test_home_page_shows_landing(make_client):
    client = make_client(FakeScraper("TunisiaNet"))
    page = client.get("/").get_data(as_text=True)
    assert "How it works" in page
    assert "Not sure where to start?" in page


def test_empty_query_shows_landing(make_client):
    client = make_client(FakeScraper("TunisiaNet"))
    assert "How it works" in client.get("/search?q=++").get_data(as_text=True)


def test_results_are_sorted_with_lowest_price_highlighted(make_client):
    store = FakeScraper("TunisiaNet", [
        make_product(name="RTX 5060 B", price=2000),
        make_product(name="RTX 5060 A", price=1500),
    ])
    page = make_client(store).get("/search?q=rtx+5060").get_data(as_text=True)
    assert page.index("RTX 5060 A") < page.index("RTX 5060 B")
    assert "Lowest price" in page
    assert "+500 DT" in page                     # B is 500 DT above the lowest


def test_price_range_is_shown(make_client):
    store = FakeScraper("TunisiaNet", [make_product(name="RTX a", price=1500),
                                       make_product(name="RTX b", price=2100)])
    page = make_client(store).get("/search?q=rtx").get_data(as_text=True)
    assert "Prices range from <strong>1 500 DT</strong> to <strong>2 100 DT</strong>" in page


def test_points_to_cheapest_in_stock_when_lowest_is_out(make_client):
    store = FakeScraper("Zoom", [make_product("Zoom", "RTX a", price=1000, status="out"),
                                 make_product("Zoom", "RTX b", price=1200, status="in")])
    page = make_client(store).get("/search?q=rtx").get_data(as_text=True)
    assert "The lowest price is out of stock" in page
    assert "1 200 DT at Zoom" in page


def test_no_in_stock_hint_when_lowest_is_available(make_client):
    store = FakeScraper("Zoom", [make_product(name="RTX a", price=1000, status="in"),
                                 make_product(name="RTX b", price=1200, status="out")])
    page = make_client(store).get("/search?q=rtx").get_data(as_text=True)
    assert "The lowest price is out of stock" not in page


def test_pagination_splits_results(make_client):
    client = make_client(FakeScraper("TunisiaNet", rtx(45)))
    page3 = client.get("/search?q=rtx+5060&page=3").get_data(as_text=True)
    assert "41–45" in page3
    assert page3.count('class="tile') == 5
    # Out-of-range pages are clamped to the last one.
    assert "41–45" in client.get("/search?q=rtx+5060&page=99").get_data(as_text=True)


def test_failed_store_is_reported_and_others_still_show(make_client, blocked):
    good = FakeScraper("TunisiaNet", rtx(3))
    bad = FakeScraper("SpaceNet", error=blocked)
    page = make_client(good, bad).get("/search?q=rtx+5060").get_data(as_text=True)
    assert "Carte RTX 5060 n0" in page
    assert 'class="notice"' in page
    assert "SpaceNet</strong> is blocking automated requests" in page
    assert "Try again" in page


def test_unexpected_scraper_crash_is_contained(make_client):
    bad = FakeScraper("Zoom", error=ValueError("selector broke"))
    page = make_client(FakeScraper("TunisiaNet", rtx(2)), bad).get(
        "/search?q=rtx+5060").get_data(as_text=True)
    assert "Carte RTX 5060 n0" in page
    assert "Zoom</strong> sent a page we couldn&#39;t read" in page


def test_all_stores_down(make_client, blocked):
    page = make_client(FakeScraper("TunisiaNet", error=blocked)).get(
        "/search?q=rtx").get_data(as_text=True)
    assert "None of the stores could be reached" in page


def test_no_results_gives_tips(make_client):
    page = make_client(FakeScraper("TunisiaNet")).get("/search?q=zzz").get_data(as_text=True)
    assert "No products found" in page
    assert "Check the spelling" in page


def test_filters_that_hide_everything_offer_a_way_out(make_client):
    store = FakeScraper("TunisiaNet", [make_product(name="Câble HDMI", price=20)])
    page = make_client(store).get("/search?q=rtx+5060").get_data(as_text=True)
    assert "your filters hid all of them" in page
    assert "Show partial matches" in page
    assert "exact=0" in page


def test_in_stock_filter_message(make_client):
    store = FakeScraper("TunisiaNet", rtx(2, status="out"))
    page = make_client(store).get("/search?q=rtx+5060&stock=1").get_data(as_text=True)
    assert "Include out-of-stock products" in page


def test_results_are_cached_between_requests(make_client):
    store = FakeScraper("TunisiaNet", rtx(30))
    client = make_client(store)
    client.get("/search?q=rtx+5060")
    client.get("/search?q=RTX+5060&page=2&sort=price_desc")  # same query, other case
    assert store.calls == 1


def test_refresh_skips_the_cache_and_is_not_carried_over(make_client, blocked):
    store = FakeScraper("TunisiaNet", rtx(30))
    client = make_client(store, FakeScraper("SpaceNet", error=blocked))
    client.get("/search?q=rtx+5060")
    page = client.get("/search?q=rtx+5060&refresh=1").get_data(as_text=True)
    assert store.calls == 2
    # Pagination links on the refreshed page don't keep refresh=1.
    assert "page=2" in page
    assert "refresh=1&amp;page" not in page and "page=2&amp;refresh" not in page


def test_failed_searches_are_cached_for_less_time(tmp_path, blocked, monkeypatch):
    saved = []
    app = create_app({
        "SCRAPERS": [FakeScraper("TunisiaNet", rtx(1)), FakeScraper("SpaceNet", error=blocked)],
        "CACHE_PATH": str(tmp_path / "c.sqlite3"),
    })
    cache = app.extensions["search_cache"]
    real_set = cache.set
    monkeypatch.setattr(cache, "set", lambda q, r, ttl: (saved.append(ttl), real_set(q, r, ttl)))
    app.test_client().get("/search?q=rtx")
    assert saved == [app_module.ERROR_CACHE_SECONDS]


def test_invalid_sort_falls_back_to_price(make_client):
    store = FakeScraper("TunisiaNet", [make_product(name="RTX b", price=2),
                                       make_product(name="RTX a", price=1)])
    page = make_client(store).get("/search?q=rtx&sort=bogus").get_data(as_text=True)
    assert page.index("RTX a") < page.index("RTX b")


def test_list_view(make_client):
    page = make_client(FakeScraper("TunisiaNet", rtx(2))).get(
        "/search?q=rtx+5060&view=list").get_data(as_text=True)
    assert "<table>" in page


def test_debug_mode_is_off_by_default(tmp_path):
    app = create_app({"CACHE_PATH": str(tmp_path / "c.sqlite3")})
    assert app.debug is False
