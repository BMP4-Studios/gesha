# Gesha

<img src="assets/logo.png" alt="Gesha Logo" width="300">

Gesha is a local-first specialty coffee discovery and cart optimization CLI. It scrapes product metadata from supported Canadian roasters (see the [roaster list](assets/roaster_list.md)), stores the catalog in a local SQLite database, and recommends preference-matched carts that reach each roaster's advertised free-shipping threshold.

Gesha currently:

- Scrapes coffee listings from the [roaster list](assets/roaster_list.md).
- Extracts metadata such as origin, producer, process, varietal, altitude, tasting notes, roast style, price, bag
  size, availability, and product URL when the source provides it
- Updates existing products and removes stale products after a successful scrape
- Stores the catalog in `gesha.db` in the directory where the CLI is run
- Lists and filters cached products without contacting roaster websites
- Stores Shopify variants and defaults to the smallest available bag
- Compares coffee prices by calculating the cost per 100 grams
- Builds preference-matched cart recommendations with ordered include keywords, exclusion keywords, and Shopify cart links

## Requirements

- Python 3.14
- Internet access for scraping roaster websites

The cached `list` and `show` commands do not require internet access once data has been scraped.

## Installation

Create and activate a virtual environment.

**macOS/Linux:**

```bash
python3.14 -m venv .venv
source .venv/bin/activate
```

**Windows PowerShell:**

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install Gesha in editable mode:

```bash
python -m pip install --upgrade pip
python -m pip install -e . # or `python -m pip install -e ".[dev]"` for development mode
```

## Usage

Here are a few common CLI commands; run `gesha --help` or `gesha <command> --help` for all CLI options.

### Scraping and Listing
```bash
# Refresh every supported roaster and displays the refreshed catalog
gesha

# Refresh every supported roaster (exact same as gesha without args)
gesha scrape

# Refresh one roaster
gesha scrape traffic

# Back up gesha.db, wipe the cache, recreate tables, and scrape every roaster
gesha rebuild

# List previously scraped coffees without making network requests
gesha list

# List previously scraped coffees from a specific roaster
gesha list traffic

# Filter the cached catalog (gesha list --help for all options)
gesha list --process washed

# Show all stored fields for one coffee with catalog ID 123
gesha show 123
```

### Getting Shopping Cart Recommendations

```bash
# Recommend carts for every supported roaster
gesha cart

# Optimize cart for one roaster
gesha cart traffic
```

## Cart preferences

Edit `cart_preferences.txt` to describe the coffees you want. Add one case-insensitive include keyword per line, ordered from most important to least important:

```text
natural
anaerobic
co-ferment
peach
mango
wilton benitez
! decaf
! dark roast
```

Include keywords are matched against the coffee name, origin, producer, process, varietal, altitude, roast style, and tasting notes. A coffee is eligible when it matches at least one include keyword and no exclusion keyword. Prefix a keyword with `!` to exclude coffees that match it, such as `! decaf` or `! dark roast`. Blank lines and lines beginning with `#` are ignored. If the file is missing or has no include keywords, Gesha uses its built-in fruity/natural include list.

The include keyword order is also the optimizer's preference order. A cart that covers a higher-listed keyword ranks ahead of carts that only cover lower-listed keywords; after that, Gesha uses cost and coverage tie-breakers.

The same file can set a Canadian destination (default is Ontario, Canada):

```text
@province ON
@postal-code M5V 3A8
```

For each roaster, Gesha:

1. Removes coffees that match any `!` exclusion keyword.
2. Selects the smallest available retail variant of each coffee that matches at least one include keyword, capped at 500g.
3. Adds all matching coffees to one roaster-specific cart.
4. Orders the coffees inside that cart by how strongly they match the include keywords.
5. Displays the destination, include/exclude keyword lists, bag prices, price per 100 grams, matched keywords, and a pre-filled Shopify cart link.

Run `gesha cart --help` for controls such as `--threshold`, `--no-refresh-shipping`, and an alternate `--preferences` file.

## Debugging, Tests, and Tooling

You can use the following CLI command to explain the cart eligibility for coffee ID 123 and save raw product HTML/JSON for parser debugging:

```bash
gesha debug 123
```

### Debugging missing tasting notes

Missing tasting notes usually mean the fast Shopify collection JSON does not contain the same rich copy that appears on the product page, so we need to parse the actual webpage HTML.

A quick way to debug missing tasting notes is the `fix-tasting-notes` command, which will look for the tasting notes you give it as arguments in the collection json, cached database, and raw product pages:

```bash
gesha fix-tasting-notes roguewave --search "Apricot|Chocolate|Vanilla|Orange|Hazelnut|notes|tasting"
```

If that finds surrounding HTML, copy the smallest useful snippet into the issue or prompt. For example, Rogue Wave notes appeared as:

```html
<ul class="product-taste-list">
  <li class="peach">Peach</li>
  <li class="milk-chocolate">Milk Chocolate</li>
</ul>
```

Depending on how the tasting notes are found, we need to tell the scraper to hydrate the collection and to either:

- fetch one tasting note per element:

```python
# Use this when each matched element is one note, such as <li>Peach</li>.
HYDRATE_COLLECTION_PRODUCTS = True
TASTING_NOTE_SELECTORS = ("ul.product-taste-list li",)
```

- use the `TASTING_NOTE_TEXT_SELECTORS` if one element contains multiple tasting notes, such as a short description span:

```python
HYDRATE_COLLECTION_PRODUCTS = True
TASTING_NOTE_TEXT_SELECTORS = (
    "div.product-item__short-desc span.text-color--opacity",
    *ShopifyScraper.TASTING_NOTE_TEXT_SELECTORS,
)
```

- or Use this when a stable product-page block contains repeated product facts.
```python
PRODUCT_FACT_SELECTORS = ("div.coffee-info-grid",)
```

## Tests and Tooling

Install the development dependencies, then run every CI check from VS Code with `Tasks: Run Task` > `Run tooling`, which will run all these

```bash
python -m ruff format --check .
python -m ruff check .
python -m pyright
python -m pip_audit --cache-dir .pip-audit-cache --skip-editable
python -m pytest --cov=gesha --cov-report=term-missing --cov-report=xml
python -m build
```

Tooling overview:

- Ruff formats code, checks common Python errors, and enforces import ordering
- Pyright performs static type checking
- pytest runs the test suite, while pytest-cov produces coverage reports
- pip-audit checks installed dependencies for known vulnerabilities
- build verifies that Gesha can produce source and wheel distributions

GitHub Actions runs these checks on Python 3.14 across Linux, macOS, and Windows for pushes and pull requests.

You can also run the pytest suite through the current Python environment with 
```bash
gesha test
```

## License

Gesha is licensed under the [MIT License](LICENSE).
