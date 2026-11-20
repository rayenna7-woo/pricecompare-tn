import math
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

from flask import Flask, render_template, request

from scrapers import ALL_SCRAPERS
from scrapers.base import ScraperError

app = Flask(__name__)

PER_PAGE = 20
CACHE_SECONDS = 10 * 60  # reuse a search's results for 10 minutes

# query -> (time_fetched, results). Lets you change page, sort or filters
# without downloading everything from the stores again.
_cache = {}


def run_scraper(scraper, query):
    """Run one store's search. Returns (store, products, error_message)."""
    try:
        return scraper.STORE, scraper.search(query), None
    except ScraperError as e:
        return scraper.STORE, [], str(e)
    except Exception as e:  # HTML changed, parsing bug, etc.
        return scraper.STORE, [], f"unexpected error: {e}"


def search_all_stores(query):
    """Results from every store, run in parallel, cached for CACHE_SECONDS."""
    key = query.lower()
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_SECONDS:
        return cached[1]

    with ThreadPoolExecutor(max_workers=len(ALL_SCRAPERS)) as pool:
        results = list(pool.map(lambda s: run_scraper(s, query), ALL_SCRAPERS))

    _cache[key] = (time.time(), results)
    return results


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


def url_with(**changes):
    """The current URL with some query parameters changed.

    Used for pagination and view links, so they keep the search, sort
    and filters. url_with(page=3) -> /search?q=...&sort=...&page=3
    """
    args = request.args.to_dict(flat=False)
    for key, value in changes.items():
        args[key] = [str(value)]
    return "/search?" + urlencode(args, doseq=True)


@app.route("/")
def index():
    return render_template("index.html", view=request.args.get("view", "grid"))


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    view = "list" if request.args.get("view") == "list" else "grid"
    if not query:
        return render_template("index.html", view=view)

    results = search_all_stores(query)

    # "All words" filter is ON by default. The toolbar form sends a hidden
    # exact=0 followed by the checkbox's exact=1 (only when checked), so the
    # last value wins.
    exact = request.args.getlist("exact")
    all_words = (exact[-1] if exact else "1") == "1"
    in_stock_only = request.args.get("stock") == "1"

    products = []
    stores = []  # per-store summary for the labels under the search bar
    for store, items, error in results:
        if all_words:
            items = [p for p in items if contains_all_words(p.name, query)]
        if in_stock_only:
            items = [p for p in items if p.in_stock]
        products.extend(items)
        stores.append({"name": store, "count": len(items), "error": error})

    sort = request.args.get("sort", "price")
    if sort == "price":
        products.sort(key=lambda p: p.price)
    elif sort == "price_desc":
        products.sort(key=lambda p: p.price, reverse=True)
    cheapest = min((p.price for p in products), default=None)

    # Pagination: PER_PAGE products per page.
    total = len(products)
    pages = max(1, math.ceil(total / PER_PAGE))
    try:
        page = int(request.args.get("page", 1))
    except ValueError:
        page = 1
    page = min(max(page, 1), pages)
    start = (page - 1) * PER_PAGE
    page_products = products[start:start + PER_PAGE]

    return render_template(
        "index.html",
        query=query,
        products=page_products,
        total=total,
        first_index=start + 1,
        page=page,
        pages=pages,
        cheapest=cheapest,
        stores=stores,
        sort=sort,
        view=view,
        in_stock_only=in_stock_only,
        all_words=all_words,
        url_with=url_with,
    )


if __name__ == "__main__":
    app.run(debug=True)
