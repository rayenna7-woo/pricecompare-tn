"""Shared pieces used by every store scraper."""
import re
import time
from dataclasses import dataclass

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}
TIMEOUT = 20

# How many result pages to read from each store per search.
# More pages = more products, but slower and more requests to the stores.
MAX_STORE_PAGES = 2
DELAY_BETWEEN_PAGES = 0.5  # seconds, to be polite to the stores


@dataclass
class Product:
    """One product found on one store. Every scraper returns a list of these."""
    store: str
    name: str
    price: float | None     # in DT, None if the price couldn't be read
    price_text: str         # the price as shown on the site, e.g. "1 469,000 DT"
    status: str             # "in" (in stock), "order" (on order) or "out"
    stock_text: str
    url: str
    image: str | None = None

    @property
    def in_stock(self) -> bool:
        return self.status == "in"


class ScraperError(Exception):
    """Raised when a store can't be scraped (blocked, down, HTML changed...)."""


def fetch(url: str, params: dict | None = None) -> str:
    """Download a page and return its HTML. Raises ScraperError on failure."""
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise ScraperError(f"network error: {e}") from e

    if "Just a moment..." in r.text and "challenges.cloudflare.com" in r.text:
        raise ScraperError("this store blocks automated access (Cloudflare bot check)")
    if r.status_code == 403:
        raise ScraperError("blocked by the site (403)")
    if r.status_code != 200:
        raise ScraperError(f"HTTP {r.status_code}")
    return r.text


def fetch_pages(get_page, max_pages: int = MAX_STORE_PAGES) -> list[Product]:
    """Call get_page(1), get_page(2)... and combine the results.

    Stops early when a page brings no new products (we went past the last
    page; some stores then repeat the last page instead of returning nothing).
    Only page 1 errors are raised: if page 2 fails, we keep page 1's results.
    """
    products, seen = [], set()
    for page in range(1, max_pages + 1):
        if page > 1:
            time.sleep(DELAY_BETWEEN_PAGES)
        try:
            items = get_page(page)
        except ScraperError:
            if page == 1:
                raise
            break
        new = [p for p in items if p.url not in seen]
        if not new:
            break
        seen.update(p.url for p in new)
        products.extend(new)
    return products


def parse_price(text: str) -> float | None:
    """Turn '1 469,000 DT' into 1469.0. Returns None if no number is found."""
    # Keep only digits and the decimal comma, then swap the comma for a dot.
    cleaned = re.sub(r"[^\d,]", "", text).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def stock_status(text: str) -> str:
    """Classify the store's stock text into "in", "order" or "out"."""
    text = text.lower()
    if "hors stock" in text or "rupture" in text or "épuisé" in text:
        return "out"
    if "commande" in text or "arrivage" in text:
        return "order"
    if "en stock" in text or "disponible" in text:
        return "in"
    return "out"


def text_of(parent, selector: str) -> str:
    """Text of the first element matching `selector` inside `parent`, or ''."""
    tag = parent.select_one(selector)
    return tag.get_text(" ", strip=True) if tag else ""


LAZY_IMAGE_ATTRS = ("data-src", "data-original", "data-lazy-src", "src")


def image_of(parent, selector: str = "img") -> str | None:
    """Image URL, handling lazy-loaded images.

    Lazy-loading stores put a tiny inline placeholder (a data: URI) in `src`
    and the real URL in an attribute such as data-src or data-original
    (Zoom does this for every product after the first).
    """
    img = parent.select_one(selector)
    if not img:
        return None
    for attr in LAZY_IMAGE_ATTRS:
        url = img.get(attr)
        if url and not url.startswith("data:"):
            return url
    return None


def make_product(store, name, price_text, stock_text, url, image) -> Product | None:
    """Build a Product, or return None if it has no price (not buyable)."""
    price = parse_price(price_text)
    if price is None:
        return None
    return Product(
        store=store,
        name=name,
        price=price,
        price_text=price_text,
        status=stock_status(stock_text),
        stock_text=stock_text or "Unknown",
        url=url,
        image=image,
    )
