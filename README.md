# PriceCompare TN

Compare tech prices across Tunisian online stores in one search.

PriceCompare TN is a small Flask web app that searches **TunisiaNet**, **Zoom** and **SpaceNet** at the same time, merges the results and shows them sorted by price, with stock status, filters and pagination.

## Features

- **One search, three stores.** The stores are scraped in parallel, so a search takes about as long as the slowest store.
- **Sorting and filters.** Sort by lowest price, highest price or store order. Optionally keep only products in stock, or only products whose name contains every word you searched (accent-insensitive, so `rtx5060` also matches `RTX 5060`).
- **Two layouts.** A Bento-style grid that highlights the cheapest product and shows results per store, and a compact table view.
- **Lowest price highlighted** in both layouts.
- **Fast paging.** Results are cached for 10 minutes, so changing page, sort or filters doesn't hit the stores again.
- **Graceful failures.** If a store is down or blocks the request, the others still show and that store is marked "unavailable".
- **Light and dark mode.** Follows your system setting, with a toggle button that remembers your choice.
- **Accessible UI.** WCAG AA contrast, visible keyboard focus, 44px touch targets, and support for "reduce motion".

## Tech stack

| Part | Tools |
| --- | --- |
| Backend | Python 3.10+, Flask |
| Scraping | requests, BeautifulSoup 4, lxml |
| Frontend | Jinja template, plain CSS with design tokens, a little vanilla JS (theme toggle only) |

No database and no build step.

## Getting started

### 1. Clone the repository

```bash
git clone https://github.com/rayenna7-woo/pricecompare-tn.git
cd pricecompare-tn
```

### 2. Create a virtual environment and install dependencies

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Run the app

```bash
python app.py
```

Then open <http://127.0.0.1:5000> and search for a product, for example `RTX 5060`.

> The app runs in Flask's debug mode and is meant for local use only. Don't expose it to the internet as is.

## Search URL parameters

Every search state lives in the URL, so results can be bookmarked or shared.

| Parameter | Values | Default |
| --- | --- | --- |
| `q` | search text | (required) |
| `sort` | `price`, `price_desc`, `relevance` (store order) | `price` |
| `exact` | `1` = all words must match, `0` = off | `1` |
| `stock` | `1` = in stock only | off |
| `view` | `grid`, `list` | `grid` |
| `page` | page number (20 products per page) | `1` |

Example: `/search?q=rtx+5060&sort=price&stock=1&view=list`

## Project structure

```
.
├── app.py               # Flask routes, caching, filtering, sorting, pagination
├── requirements.txt
├── scrapers/
│   ├── __init__.py      # ALL_SCRAPERS: the list of stores to search
│   ├── base.py          # Product model, HTTP fetching, price/stock parsing helpers
│   ├── tunisianet.py    # One module per store
│   ├── zoom.py
│   ├── spacenet.py
│   └── test.py          # Debug helper: saves a store's search page to HTML
└── templates/
    └── index.html       # The whole UI: markup, design tokens, styles, theme toggle
```

## How it works

1. `app.py` receives `/search?q=...` and runs every scraper in `ALL_SCRAPERS` in a thread pool.
2. Each scraper downloads up to 2 result pages from its store (with a short pause between pages) and turns every product card into a `Product` (store, name, price, stock status, URL, image). Products without a price are skipped.
3. The combined results are cached per query for 10 minutes.
4. Filters and sorting are applied, the list is split into pages of 20, and `templates/index.html` renders it.

## Adding a store

1. Create `scrapers/mystore.py` with a `STORE` name and a `search(query)` function that returns a list of `Product`. The helpers in `base.py` (`fetch`, `fetch_pages`, `make_product`, `text_of`, `image_of`) do most of the work. `zoom.py` is a good template.
2. Add the module to `ALL_SCRAPERS` in `scrapers/__init__.py`.
3. Optionally give it a colour: add a `--color-store-mystore` token (light and dark values) in `templates/index.html` and a `.mystore { --store-color: var(--color-store-mystore); }` rule.

## Design

The interface follows a **Minimalism & Swiss Style** direction: Inter type, a strict black-and-white palette with a single red accent, square corners, no shadows, and a grid-based layout. All colours, type sizes, spacing, radii and motion timings are CSS custom properties defined once at the top of `templates/index.html`, with a matching dark set, so the whole theme can be adjusted in one place.

## Limitations

- Scrapers depend on each store's HTML. If a store redesigns its site, its scraper needs updating.
- Some stores may block automated requests (for example with a Cloudflare check). The app then shows that store as unavailable.
- Prices and stock are whatever the store shows at search time. Always check the store page before buying.

## Disclaimer

This is a personal learning project, not affiliated with any of the stores. It makes a small number of requests per search, waits between pages and caches results. If you run it, use it responsibly and respect each website's terms of use.

## License

[MIT](LICENSE)
