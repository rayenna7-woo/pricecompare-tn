from bs4 import BeautifulSoup

from .base import fetch, fetch_pages, image_of, make_product, text_of

STORE = "Zoom"
SEARCH_URL = "https://zoom.com.tn/recherche"


def search(query):
    return fetch_pages(lambda page: parse(fetch(
        SEARCH_URL, params={"controller": "search", "s": query, "page": page}
    )))


def parse(html):
    soup = BeautifulSoup(html, "lxml")
    products = []

    for box in soup.select(".js-product-miniature"):
        title = box.select_one(".product-name a")
        if not title:
            continue

        # Discontinued products have no price block (just a "Détails"
        # button): make_product returns None for them and we skip them.
        product = make_product(
            store=STORE,
            name=title.get_text(strip=True),
            # e.g. "4 099,000 TND" with non-breaking spaces; parse_price
            # keeps only digits and the comma, so that's fine.
            price_text=text_of(box, ".product-price"),
            # "En stock", "Sur commande" or "Hors stock"
            stock_text=text_of(box, ".product-availability span"),
            url=title["href"],
            image=image_of(box, ".product-thumbnail img"),
        )
        if product:
            products.append(product)

    return products
