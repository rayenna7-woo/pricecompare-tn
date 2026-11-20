from bs4 import BeautifulSoup

from .base import fetch, fetch_pages, image_of, make_product, text_of

STORE = "TunisiaNet"
SEARCH_URL = "https://www.tunisianet.com.tn/recherche"


def search(query):
    return fetch_pages(lambda page: parse(fetch(
        SEARCH_URL, params={"controller": "search", "s": query, "page": page}
    )))


def parse(html):
    soup = BeautifulSoup(html, "lxml")
    products = []

    for box in soup.select(".item-product"):
        title = box.select_one(".product-title a")
        if not title:
            continue

        # Price and stock appear twice per box (grid + list layout):
        # select_one only takes the first one.
        product = make_product(
            store=STORE,
            name=title.get_text(strip=True),
            price_text=text_of(box, '[itemprop="price"]'),
            stock_text=text_of(box, "#stock_availability span"),
            url=title["href"],
            image=image_of(box, "img.thumbnail-img"),
        )
        if product:
            products.append(product)

    return products
