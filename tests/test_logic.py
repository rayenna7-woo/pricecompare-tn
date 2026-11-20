"""Filtering, sorting, pagination and formatting helpers."""
from app import (contains_all_words, filter_products, format_dt, friendly_error,
                 normalize, paginate, parse_page, sort_products)
from conftest import make_product


# ---------------------------------------------------------------- matching

def test_normalize_removes_accents_and_case():
    assert normalize("Écran GÉNÉRATION") == "ecran generation"


def test_contains_all_words_requires_every_word():
    assert contains_all_words("Carte graphique MSI RTX 5060", "rtx 5060")
    assert not contains_all_words("Carte graphique MSI RTX 5070", "rtx 5060")


def test_contains_all_words_ignores_accents_and_spaces():
    assert contains_all_words("Écran Gamer 27 pouces", "ecran 27")
    assert contains_all_words("Carte graphique RTX 5060", "rtx5060")


# --------------------------------------------------------------- filtering

def results_fixture():
    return [
        ("TunisiaNet", [
            make_product(name="RTX 5060 Gaming", price=1500, status="in"),
            make_product(name="RTX 5060 Ti", price=1900, status="out"),
            make_product(name="Câble HDMI", price=20, status="in"),
        ], None),
        ("SpaceNet", [], "blocked by the site (403)"),
    ]


def test_filter_all_words_drops_unrelated_products():
    products, stores = filter_products(results_fixture(), "rtx 5060", all_words=True)
    assert [p.name for p in products] == ["RTX 5060 Gaming", "RTX 5060 Ti"]
    assert stores[0] == {"name": "TunisiaNet", "raw_count": 3, "count": 2, "error": None}


def test_filter_off_keeps_everything():
    products, _ = filter_products(results_fixture(), "rtx 5060", all_words=False)
    assert len(products) == 3


def test_filter_in_stock_only():
    products, _ = filter_products(results_fixture(), "rtx 5060", all_words=True,
                                  in_stock_only=True)
    assert [p.name for p in products] == ["RTX 5060 Gaming"]


def test_filter_keeps_store_errors():
    _, stores = filter_products(results_fixture(), "rtx", all_words=True)
    assert stores[1] == {"name": "SpaceNet", "raw_count": 0, "count": 0,
                         "error": "blocked by the site (403)"}


# ----------------------------------------------------------------- sorting

def test_sort_by_price_both_directions():
    items = [make_product(price=p) for p in (300, 100, 200)]
    assert [p.price for p in sort_products(items, "price")] == [100, 200, 300]
    assert [p.price for p in sort_products(items, "price_desc")] == [300, 200, 100]


def test_sort_relevance_keeps_store_order_and_does_not_mutate():
    items = [make_product(price=p) for p in (300, 100, 200)]
    result = sort_products(items, "relevance")
    assert [p.price for p in result] == [300, 100, 200]
    assert result is not items


# -------------------------------------------------------------- pagination

def test_paginate_middle_and_last_page():
    items = list(range(45))
    assert paginate(items, 2, per_page=20)["items"] == list(range(20, 40))
    last = paginate(items, 3, per_page=20)
    assert last["items"] == list(range(40, 45))
    assert last["pages"] == 3
    assert last["start"] == 40


def test_paginate_clamps_out_of_range_pages():
    items = list(range(45))
    assert paginate(items, 99, per_page=20)["page"] == 3
    assert paginate(items, -5, per_page=20)["page"] == 1


def test_paginate_empty_list_has_one_page():
    result = paginate([], 1, per_page=20)
    assert result == {"items": [], "page": 1, "pages": 1, "start": 0}


def test_parse_page_rejects_garbage():
    assert parse_page("3") == 3
    assert parse_page("abc") == 1
    assert parse_page(None) == 1


# -------------------------------------------------------------- formatting

def test_format_dt_rounds_and_groups_thousands():
    assert format_dt(1799.0) == "1 799 DT"
    assert format_dt(49.6) == "50 DT"
    assert format_dt(None) == ""


def test_friendly_error_messages():
    assert "blocking" in friendly_error("this store blocks automated access (Cloudflare bot check)")
    assert "blocking" in friendly_error("blocked by the site (403)")
    assert "respond" in friendly_error("network error: timed out")
    assert "error page" in friendly_error("HTTP 500")
    assert "couldn't read" in friendly_error("unexpected error: 'NoneType'")
