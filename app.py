import math
import os
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode

from flask import Flask, render_template, request

from cache import SearchCache
from scrapers import ALL_SCRAPERS
from scrapers.base import ScraperError

PER_PAGE = 20
CACHE_SECONDS = 10 * 60      # reuse a search's results for 10 minutes
ERROR_CACHE_SECONDS = 60     # ...but retry sooner if a store failed
SORTS = ("price", "price_desc", "relevance")


# --------------------------------------------------------------------------
# Scraping
# --------------------------------------------------------------------------

def run_scraper(scraper, query):
    """Run one store's search. Returns (store, products, error_message)."""
    try:
        return scraper.STORE, scraper.search(query), None
    except ScraperError as e:
        return scraper.STORE, [], str(e)
    except Exception as e:  # HTML changed, parsing bug, etc.
        return scraper.STORE, [], f"unexpected error: {e}"


def scrape_all(scrapers, query):
    """Run every scraper in parallel. Returns a list of (store, products, error)."""
    with ThreadPoolExecutor(max_workers=max(1, len(scrapers))) as pool:
        return list(pool.map(lambda s: run_scraper(s, query), scrapers))


# --------------------------------------------------------------------------
# Filtering, sorting, pagination (pure functions, easy to test)
# --------------------------------------------------------------------------

def normalize(text):
    """Lowercase and remove accents, so 'Génération' matches 'generation'."""
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def contains_all_words(name, query):
    """True if every word of the query appears in the product name.

    Also checks the name with spaces removed, so 'rtx5060' matches 'RTX 5060'.
    """
    name = normalize(name)
    name_no_spaces = name.replace(" ", "")
    return all(
        word in name or word in name_no_spaces
        for word in normalize(query).split()
    )


def filter_products(results, query, all_words=True, in_stock_only=False):
    """Apply the toolbar filters to every store's results.

    Returns (products, stores): the products that pass, and a per-store
    summary with how many products the store returned (`raw_count`), how
    many survived the filters (`count`) and its error message, if any.
    """
    products, stores = [], []
    for store, items, error in results:
        kept = items
        if all_words:
            kept = [p for p in kept if contains_all_words(p.name, query)]
        if in_stock_only:
            kept = [p for p in kept if p.in_stock]
        products.extend(kept)
        stores.append({
            "name": store,
            "raw_count": len(items),
            "count": len(kept),
            "error": error,
        })
    return products, stores


def sort_products(products, sort):
    """Sorted copy of `products`. 'relevance' keeps the stores' own order."""
    if sort == "price":
        return sorted(products, key=lambda p: p.price)
    if sort == "price_desc":
        return sorted(products, key=lambda p: p.price, reverse=True)
    return list(products)


def parse_page(value):
    """Page number from the query string; anything invalid becomes 1."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def paginate(items, page, per_page=PER_PAGE):
    """Slice `items` into pages. `page` is clamped to the valid range."""
    pages = max(1, math.ceil(len(items) / per_page))
    page = min(max(page, 1), pages)
    start = (page - 1) * per_page
    return {
        "items": items[start:start + per_page],
        "page": page,
        "pages": pages,
        "start": start,
    }


def format_dt(value):
    """1799.0 -> '1 799 DT' (non-breaking spaces), for computed prices."""
    if value is None:
        return ""
    return f"{round(value):,}".replace(",", " ") + " DT"


def friendly_error(message):
    """Turn a scraper error into a short reason a visitor can understand."""
    text = (message or "").lower()
    if "cloudflare" in text or "403" in text or "blocked" in text:
        return "is blocking automated requests right now"
    if "network" in text or "timed out" in text or "timeout" in text:
        return "didn't respond in time"
    if "http" in text:
        return "returned an error page"
    return "sent a page we couldn't read"


def url_with(**changes):
    """The current URL with some query parameters changed.

    Used for pagination, view and filter links, so they keep the search,
    sort and filters. url_with(page=3) -> /search?q=...&sort=...&page=3
    Passing None removes a parameter. `refresh` (skip the cache) is never
    carried over unless asked for, so it only applies to one request.
    """
    args = request.args.to_dict(flat=False)
    args.pop("refresh", None)
    for key, value in changes.items():
        if value is None:
            args.pop(key, None)
        else:
            args[key] = [str(value)]
    return "/search?" + urlencode(args, doseq=True)


# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------

def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        SCRAPERS=ALL_SCRAPERS,
        CACHE_PATH=os.environ.get(
            "PRICECOMPARE_CACHE", str(Path(app.instance_path) / "cache.sqlite3")
        ),
        PER_PAGE=PER_PAGE,
    )
    if config:
        app.config.update(config)

    cache = SearchCache(app.config["CACHE_PATH"])
    app.extensions["search_cache"] = cache
    app.jinja_env.filters["dt"] = format_dt
    app.jinja_env.filters["friendly_error"] = friendly_error

    def search_all_stores(query, refresh=False):
        """Results from every store, cached on disk. `refresh` skips the cache."""
        key = query.lower()
        cached = None if refresh else cache.get(key)
        if cached is not None:
            return cached
        results = scrape_all(app.config["SCRAPERS"], query)
        failed = any(error for _, _, error in results)
        cache.set(key, results, ERROR_CACHE_SECONDS if failed else CACHE_SECONDS)
        return results

    @app.route("/")
    def index():
        return render_template("index.html", view=request.args.get("view", "grid"))

    @app.route("/search")
    def search():
        query = request.args.get("q", "").strip()
        view = "list" if request.args.get("view") == "list" else "grid"
        if not query:
            return render_template("index.html", view=view)

        # "All words" filter is ON by default. The toolbar form sends a hidden
        # exact=0 followed by the checkbox's exact=1 (only when checked), so
        # the last value wins.
        exact = request.args.getlist("exact")
        all_words = (exact[-1] if exact else "1") == "1"
        in_stock_only = request.args.get("stock") == "1"
        sort = request.args.get("sort", "price")
        if sort not in SORTS:
            sort = "price"

        results = search_all_stores(query, refresh=request.args.get("refresh") == "1")
        products, stores = filter_products(results, query, all_words, in_stock_only)
        products = sort_products(products, sort)

        prices = [p.price for p in products]
        cheapest = min(prices, default=None)
        priciest = max(prices, default=None)
        # If the lowest price is out of stock, point out the cheapest one
        # that can actually be bought now.
        lowest_in_stock = any(p.in_stock for p in products if p.price == cheapest)
        cheapest_available = None if lowest_in_stock else min(
            (p for p in products if p.in_stock), key=lambda p: p.price, default=None)

        pg = paginate(products, parse_page(request.args.get("page")),
                      app.config["PER_PAGE"])

        return render_template(
            "index.html",
            query=query,
            products=pg["items"],
            total=len(products),
            raw_total=sum(s["raw_count"] for s in stores),
            first_index=pg["start"] + 1,
            page=pg["page"],
            pages=pg["pages"],
            cheapest=cheapest,
            priciest=priciest,
            cheapest_available=cheapest_available,
            stores=stores,
            failed_stores=[s for s in stores if s["error"]],
            sort=sort,
            view=view,
            in_stock_only=in_stock_only,
            all_words=all_words,
            url_with=url_with,
        )

    return app


app = create_app()


if __name__ == "__main__":
    # Debug mode (auto-reload + the interactive debugger) is opt-in and only
    # for local development: set FLASK_DEBUG=1. The server always binds to
    # 127.0.0.1 so it isn't reachable from other machines.
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
