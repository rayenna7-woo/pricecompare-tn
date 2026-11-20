"""Store parsers (against saved HTML fixtures) and the shared HTTP helpers."""
from pathlib import Path

import pytest
import requests

from scrapers import base, spacenet, tunisianet, zoom
from scrapers.base import ScraperError, fetch, fetch_pages, parse_price, stock_status

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


# ------------------------------------------------------------------ parsers

def test_tunisianet_parser():
    products = tunisianet.parse(fixture("tunisianet_search.html"))
    assert [p.price for p in products] == [1469.0, 1799.0, 1849.0]
    assert products[1].name == "Carte graphique PNY GeForce RTX 5060 / 8 Go GDDR7"
    assert all(p.store == "TunisiaNet" for p in products)
    assert all(p.status == "in" and p.stock_text == "En stock" for p in products)
    assert all(p.url.startswith("https://www.tunisianet.com.tn/") for p in products)
    assert all(p.image for p in products)


def test_zoom_parser():
    products = zoom.parse(fixture("zoom_search.html"))
    assert [p.price for p in products] == [480.0, 310.0, 1149.0]
    assert [p.status for p in products] == ["in", "in", "order"]
    assert products[2].stock_text == "En arrivage"
    assert all(p.url.startswith("https://zoom.com.tn/") for p in products)


def test_zoom_lazy_images_use_the_real_url():
    # Cards 2 and 3 have a data: placeholder in src and the photo in data-original.
    products = zoom.parse(fixture("zoom_search.html"))
    assert all(p.image.startswith("https://zoom.com.tn/") for p in products)


def test_image_of_ignores_inline_placeholders():
    from bs4 import BeautifulSoup
    html = '<div><img src="data:image/svg+xml,%3Csvg%3E" data-original="https://x/a.jpg"></div>'
    assert base.image_of(BeautifulSoup(html, "lxml")) == "https://x/a.jpg"
    only_placeholder = '<div><img src="data:image/svg+xml,%3Csvg%3E"></div>'
    assert base.image_of(BeautifulSoup(only_placeholder, "lxml")) is None


def test_spacenet_parser():
    products = spacenet.parse(fixture("spacenet_search.html"))
    assert [p.price for p in products] == [6979.0, 4169.0, 3679.0]
    assert "Gén" in products[0].name          # accents decoded correctly
    assert all(p.status == "in" for p in products)
    assert all(p.url.startswith("https://spacenet.tn/") for p in products)


@pytest.mark.parametrize("module", [tunisianet, zoom, spacenet])
def test_parsers_return_nothing_for_unrelated_html(module):
    assert module.parse("<html><body><p>Aucun produit</p></body></html>") == []


# ------------------------------------------------------------------ helpers

@pytest.mark.parametrize("text, expected", [
    ("1 469,000 DT", 1469.0),
    ("4 099,000 TND", 4099.0),
    ("59,900 DT", 59.9),
    ("Prix sur demande", None),
    ("", None),
])
def test_parse_price(text, expected):
    assert parse_price(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("En stock", "in"),
    ("Disponible", "in"),
    ("Sur commande", "order"),
    ("En arrivage", "order"),
    ("Hors stock", "out"),
    ("Rupture de stock", "out"),
    ("Épuisé", "out"),
    ("", "out"),
])
def test_stock_status(text, expected):
    assert stock_status(text) == expected


def test_make_product_skips_items_without_price():
    assert base.make_product("Zoom", "PC", "Détails", "", "https://x", None) is None


# --------------------------------------------------------------- failures

class FakeResponse:
    def __init__(self, status_code=200, text="<html></html>"):
        self.status_code = status_code
        self.text = text


def test_fetch_raises_on_403(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(403))
    with pytest.raises(ScraperError, match="403"):
        fetch("https://example.com")


def test_fetch_raises_on_server_error(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(503))
    with pytest.raises(ScraperError, match="HTTP 503"):
        fetch("https://example.com")


def test_fetch_detects_cloudflare_challenge(monkeypatch):
    page = "<title>Just a moment...</title><script src='https://challenges.cloudflare.com/x'>"
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(200, page))
    with pytest.raises(ScraperError, match="Cloudflare"):
        fetch("https://example.com")


def test_fetch_wraps_network_errors(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("no route to host")
    monkeypatch.setattr(requests, "get", boom)
    with pytest.raises(ScraperError, match="network error"):
        fetch("https://example.com")


def test_store_search_turns_a_block_into_scraper_error(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(403))
    with pytest.raises(ScraperError):
        zoom.search("rtx 5060")


# --------------------------------------------------------------- paging

@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(base.time, "sleep", lambda s: None)


def test_fetch_pages_combines_pages_and_stops_on_repeats(no_sleep):
    p1 = [base.make_product("Zoom", "A", "10", "En stock", "u1", None)]
    p2 = [base.make_product("Zoom", "B", "20", "En stock", "u2", None)]
    pages = {1: p1, 2: p2, 3: p2}
    assert [p.url for p in fetch_pages(lambda n: pages[n], max_pages=3)] == ["u1", "u2"]


def test_fetch_pages_keeps_page_one_if_page_two_fails(no_sleep):
    p1 = [base.make_product("Zoom", "A", "10", "En stock", "u1", None)]

    def get_page(n):
        if n == 2:
            raise ScraperError("HTTP 500")
        return p1

    assert [p.url for p in fetch_pages(get_page, max_pages=2)] == ["u1"]


def test_fetch_pages_raises_if_page_one_fails(no_sleep):
    def get_page(n):
        raise ScraperError("blocked by the site (403)")

    with pytest.raises(ScraperError):
        fetch_pages(get_page)
