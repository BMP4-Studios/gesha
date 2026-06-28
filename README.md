# Gesha

<img src="assets/logo.png" alt="Gesha Logo" width="300">

Gesha is a local-first specialty coffee discovery and cart optimization CLI. It scrapes product metadata from
supported Canadian roasters, stores the catalog in a local SQLite database, and recommends preference-matched carts
that reach each roaster's advertised free-shipping threshold.

## Current scope

Gesha currently:

- Scrapes coffee listings from De Mello, Traffic, Porte Bleue, Colorfull Coffee, The Angry Roaster, and the first
  expanded Shopify cohort
- Extracts metadata such as origin, producer, process, varietal, altitude, tasting notes, roast style, price, bag
  size, availability, and product URL when the source provides it
- Updates existing products and removes stale products after a successful scrape
- Stores the catalog in `gesha.db` in the directory where the CLI is run
- Lists and filters cached products without contacting roaster websites
- Stores Shopify variants and defaults to the smallest available bag
- Compares coffee prices by calculating the cost per 100 grams
- Builds preference-matched cart recommendations with ordered include keywords, exclusion keywords, and Shopify cart links

## Data cleanup

The scraper keeps source data recognizable rather than trying to impose a comprehensive coffee taxonomy.
Currently, cleanup is deliberately limited:

- Product titles, origins, and processes are lowercased, Unicode-normalized, stripped of decorative characters,
  and have repeated whitespace collapsed
- Tasting-note strings are split on common separators, trimmed, lowercased, and kept in source order
- Structured fields are extracted from labeled product-page data when available, with Shopify descriptions, tags,
  variants, and limited title parsing used as fallbacks
- Other values, such as producer, varietal, altitude, roast style, and bag size, are generally stored as supplied by
  the roaster

Missing metadata remains empty and is displayed as `NONE`; Gesha does not infer facts that the source does not
provide.

## Requirements

- Python 3.14
- Internet access for scraping roaster websites

The cached `list`, `cache`, and `show` commands do not require internet access once data has been scraped.

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
python -m pip install -e . # or `python -m pip install -e ".[dev]" for development mode
```

The package and dependency definitions in `pyproject.toml` are authoritative. `requirements.txt` is retained as a
convenient flat dependency list.

## Usage

Running `gesha` without a subcommand refreshes every supported roaster and displays the refreshed catalog:

```bash
gesha
```

Common commands:

```bash
# Create the local database without scraping
gesha init

# Refresh every supported roaster
gesha scrape

# Refresh every supported roaster one at a time, which is gentler on storefronts
gesha scrape --serial

# Limit scrape concurrency explicitly
gesha scrape --workers 2

# Refresh one roaster
gesha scrape traffic

# Back up gesha.db, wipe the cache, recreate tables, and scrape every roaster
gesha rebuild

# List previously scraped coffees without making network requests
gesha list

# Filter the cached catalog
gesha list --process washed
gesha list --flavour berry
gesha list --roaster traffic
gesha list --available

# Show all stored fields for one catalog ID
gesha show 1

# Recommend carts for every supported roaster
gesha cart

# Optimize one roaster and prefill a Canadian checkout destination
gesha cart traffic --postal-code "M5V 3A8"

# Override the published free-shipping threshold
gesha cart demello --threshold 50

# Explain why one cached coffee is included in or skipped from cart recommendations
gesha cart-debug 25

# Download a roaster's raw Shopify collection JSON to debug/<roaster>.json
gesha json traffic

# Save a product's raw HTML and Shopify JSON for parser debugging
gesha debug 1

# Gather collection and product debug files for coffees missing tasting notes
gesha fix-tasting-notes roguewave --search "Apricot|Chocolate|Vanilla|Orange|Hazelnut|notes|tasting"
```

`gesha cache` is an alias for `gesha list`. Run `gesha --help` or `gesha <command> --help` for the complete command
reference.

Supported scrape keys are:

```text
demello
traffic
portebleue
colorfull
angry
houseoffunk
roguewave
quietly
kohi
subtext
artery
ethica
rabbithole
escape
pirates
94celcius
cafepista
jungle
zaandklo
nektar
september
monogram
narval
all
```

## Debugging missing tasting notes

Missing tasting notes usually mean the fast Shopify collection JSON does not contain the same rich copy that appears on
the product page. Use `gesha json` to inspect the collection feed and `gesha debug` to inspect one cached product's page
HTML plus product JSON.

Start with a cached product that is missing notes:

```bash
gesha scrape roguewave
gesha list --roaster roguewave
gesha show 95
```

Dump the product's raw data:

```bash
gesha debug 95
```

Open the URL printed at the top of `debug/debug_95.txt`, copy one visible tasting note from the webpage, then search the
debug file for that exact note:

```bash
grep -nEi "Peach" debug/debug_95.txt
```

If that finds surrounding HTML, copy the smallest useful snippet into the issue or prompt. For example, Rogue Wave notes
appeared as:

```html
<ul class="product-taste-list">
  <li class="peach">Peach</li>
  <li class="milk-chocolate">Milk Chocolate</li>
</ul>
```

That snippet tells the scraper fix to hydrate the product page and read notes with a selector such as
`ul.product-taste-list li`. If notes are absent from `debug/debug_<id>.txt`, inspect the collection feed too:

```bash
gesha json roguewave
grep -nEi "Peach|Milk Chocolate|Apple|Almond|Tangerine|notes|tasting" debug/roguewave.json
```

Most Shopify tasting-note fixes should be declarative once the HTML snippet is found:

```python
# Use this when each matched element is one note, such as <li>Peach</li>.
HYDRATE_COLLECTION_PRODUCTS = True
TASTING_NOTE_SELECTORS = ("ul.product-taste-list li",)

# Use this when one matched element contains the note text, such as a short description span.
HYDRATE_COLLECTION_PRODUCTS = True
TASTING_NOTE_TEXT_SELECTORS = (
    "div.product-item__short-desc span.text-color--opacity",
    *ShopifyScraper.TASTING_NOTE_TEXT_SELECTORS,
)

# Use this when a stable product-page block contains repeated product facts.
PRODUCT_FACT_SELECTORS = ("div.coffee-info-grid",)
```

To automate that evidence-gathering loop for cached products missing notes, use:

```bash
gesha fix-tasting-notes roguewave --search "Peach|Milk Chocolate|Apple|Almond|Tangerine|notes|tasting"
```

This writes `debug/roguewave.json`, dumps up to five cached Rogue Wave products with no tasting notes to
`debug/debug_<id>.txt`, and prints matching lines from each file. Increase `--limit` to inspect more products.

## Cart preferences

Edit `cart_preferences.txt` to describe the coffees you want. Add one case-insensitive include keyword per line,
ordered from most important to least important:

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

Include keywords are matched against the coffee name, origin, producer, process, varietal, altitude, roast style, and
tasting notes. A coffee is eligible when it matches at least one include keyword and no exclusion keyword. Prefix a
keyword with `!` to exclude coffees that match it, such as `! decaf` or `! dark roast`. Blank lines and lines beginning
with `#` are ignored. If the file is missing or has no include keywords, Gesha uses its built-in fruity/natural
include list.

The include keyword order is also the optimizer's preference order. A cart that covers a higher-listed keyword ranks
ahead of carts that only cover lower-listed keywords; after that, Gesha uses cost and coverage tie-breakers.

The same file can set a Canadian destination:

```text
@province ON
@postal-code M5V 3A8
```

Command-line `--province` and `--postal-code` values override the file. A Canadian postal code is validated,
normalized, and used to infer its province when no province is supplied. Ontario, Canada is the default destination.

For each roaster, Gesha:

1. Removes coffees that match any `!` exclusion keyword.
2. Selects the smallest available retail variant of each coffee that matches at least one include keyword, capped at
   roughly 1 lb / 454 g.
3. Adds all matching coffees to one roaster-specific cart.
4. Orders the coffees inside that cart by how strongly they match the include keywords.
5. Displays the destination, include/exclude keyword lists, bag prices, price per 100 grams, matched keywords, and a
   pre-filled Shopify cart link.

Gesha checks each roaster's public shipping page and falls back to a configured threshold if the page cannot be
read or its wording is not recognized. Shipping eligibility remains an estimate because discounts, destination
restrictions, and checkout rules can change; confirm the final shipping rate at checkout. Use
`--no-refresh-shipping` for an offline recommendation or `--threshold` to supply a known amount.

Run `gesha cart --help` for controls such as `--threshold`, `--no-refresh-shipping`, and an alternate `--preferences` file.

## Development

Install the development dependencies, then run every CI check from VS Code with
`Tasks: Run Task` > `Run tooling`.

The equivalent terminal commands are:

```bash
python -m ruff format --check .
python -m ruff check .
python -m pyright
python -m pip_audit --cache-dir .pip-audit-cache --skip-editable
python -m pytest --cov=gesha --cov-report=term-missing --cov-report=xml
python -m build
```

Run only the tests with either:

```bash
python -m pytest
gesha test
```

Tooling overview:

- Ruff formats code, checks common Python errors, and enforces import ordering
- Pyright performs static type checking
- pytest runs the test suite, while pytest-cov produces coverage reports
- pip-audit checks installed dependencies for known vulnerabilities
- build verifies that Gesha can produce source and wheel distributions

GitHub Actions runs these checks on Python 3.14 across Linux, macOS, and Windows for pushes and pull requests.

## License

Gesha is licensed under the [MIT License](LICENSE).
