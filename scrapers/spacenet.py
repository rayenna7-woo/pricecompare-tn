from bs4 import BeautifulSoup

from .base import fetch, fetch_pages, image_of, make_product, text_of

STORE = "SpaceNet"
SEARCH_URL = "https://spacenet.tn/recherche"


def search(query):
    return fetch_pages(lambda page: parse(fetch(
        SEARCH_URL, params={"controller": "search", "s": query, "page": page}
    )))


def parse(html):
    soup = BeautifulSoup(html, "lxml")
    products = []

    # The whole product card is .item-inner: the image is on the left,
    # and .right-product holds name / price / stock.
    for box in soup.select(".item-inner"):
        info = box.select_one(".right-product")
        title = info.select_one(".product_name a") if info else None
        if not title:
            continue

        product = make_product(
            store=STORE,
            name=title.get_text(strip=True),
            price_text=text_of(info, ".price"),
            # Not just "label.label": the reference ("Réf :") is also a label.
            stock_text=text_of(info, ".product-quantities .label"),
            url=title["href"],
            image=image_of(box),
        )
        if product:
            products.append(product)

    return products
