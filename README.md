# Gesha

<img src="assets/logo.png" alt="Gesha Logo" width="300">

Gesha is a local-first specialty coffee discovery and cart optimization CLI. It scrapes product metadata from
supported Canadian roasters, stores the catalog in a local SQLite database, and recommends preference-matched carts
that reach each roaster's advertised free-shipping threshold.

## Current scope

Gesha currently:

- Scrapes coffee listings from De Mello, Traffic, Porte Bleue, Colorfull Coffee, and The Angry Roaster
- Extracts metadata such as origin, producer, process, varietal, altitude, tasting notes, roast style, price, bag
  size, availability, and product URL when the source provides it
- Updates existing products and removes stale products after a successful scrape
- Stores the catalog in `gesha.db` in the directory where the CLI is run
- Lists and filters cached products without contacting roaster websites
- Stores Shopify variants and defaults to the smallest available bag
- Compares coffee prices by calculating the cost per 100 grams
- Builds preference-matched cart recommendations and Shopify cart links

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
python -m pip install -e .
```

For development, install the optional tooling dependencies as well:

```bash
python -m pip install -e ".[dev]"
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

# Refresh one roaster
gesha scrape traffic

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

# Save a product's raw HTML and Shopify JSON for parser debugging
gesha debug 1
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
all
```

## Cart preferences

Edit `cart_preferences.txt` to describe the coffees you want. Add one case-insensitive keyword per line:

```text
natural
anaerobic
co-ferment
peach
mango
wilton benitez
```

A coffee is eligible when at least one keyword appears in its name, origin, producer, process, varietal, altitude,
roast style, or tasting notes. More distinct matches produce a higher preference score. Blank lines and lines
beginning with `#` are ignored.

The same file can set a Canadian destination:

```text
@province ON
@postal-code M5V 3A8
```

Command-line `--province` and `--postal-code` values override the file. A Canadian postal code is validated,
normalized, and used to infer its province when no province is supplied. Ontario, Canada is the default destination.

For each roaster, Gesha:

1. Selects the smallest available variant of each keyword-matched coffee.
2. Finds combinations of distinct coffees that reach the free-shipping threshold.
3. Ranks carts by lowest amount above the threshold, then preference coverage and score.
4. Displays bag prices, price per 100 grams, matched keywords, and a pre-filled Shopify cart link.

Gesha checks each roaster's public shipping page and falls back to a configured threshold if the page cannot be
read or its wording is not recognized. Shipping eligibility remains an estimate because discounts, destination
restrictions, and checkout rules can change; confirm the final shipping rate at checkout. Use
`--no-refresh-shipping` for an offline recommendation or `--threshold` to supply a known amount.

Run `gesha cart --help` for controls such as `--max-bags`, `--limit`, and an alternate `--preferences` file.

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
