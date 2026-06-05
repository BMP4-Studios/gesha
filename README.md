# Gesha

# <img src="assets/gesha.png" alt="Gesha Logo" width="300">

Gesha is a local-first specialty coffee discovery and cart optimization CLI tool focused on scraping Canadian roasters, normalizing coffee metadata, and storing it in a local SQLite database.

## What it does

- Scrapes specialty coffee products from supported roasters
- Normalizes roaster, origin, process, tasting notes, price, bag size, and availability
- Stores coffee records locally in SQLite
- Provides CLI commands to query and inspect coffees

## Install

Create and activate a Python virtual environment, then install the package:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

For local development, install the package with its tooling extras:

```bash
python -m pip install -e ".[dev]"
```

## Initialize the database

```bash
gesha init
```

This creates the SQLite schema for roasters, coffees, and tasting notes.

Running `gesha` or `gesha scrape` will automatically initialize the database schema if needed.

## Requirements

- Internet access is required for scraping remote roaster pages.
- If `gesha` fails with a DNS or network error, verify your connection and retry.

## Basic usage

Refresh every supported roaster, remove stale local rows, and list the cleaned catalog:

```bash
gesha
```

Scrape a single supported roaster:

```bash
gesha scrape traffic
```

Supported default roasters are De Mello, Traffic, Porte Bleue, Colorfull, The Angry Roaster, Rogue Wave, and House of Funk. Hatch is available as an explicit custom scraper, but is not part of the default refresh because its site is less Shopify-like and less reliable:

```bash
gesha scrape hatch
```

Scrape all supported roasters (default):

```bash
gesha scrape
```

After scraping, the CLI will automatically display the cleaned local catalog.

List coffees:

```bash
gesha list
```

Filter by process:

```bash
gesha list --process washed
```

Filter by tasting note:

```bash
gesha list --flavor berry
```

Show a coffee by ID:

```bash
gesha show 1
```

## Project structure

- `gesha/` — Python package source code
- `gesha/db/` — SQLAlchemy models and session setup
- `gesha/scrapers/` — scraper implementations
- `gesha/parsers/` — HTML parsing helpers
- `gesha/normalization/` — normalization utilities
- `gesha/services/` — business logic for persistence and querying
- `gesha/cli/` — Typer CLI commands
- `tests/` — pytest test cases

## Development tooling

Run the same checks used by CI:

```bash
python -m ruff format --check .
python -m ruff check .
python -m pytest --cov=gesha --cov-report=term-missing --cov-report=xml
python -m build
```

Tooling equivalents:

- `clang-format` -> Ruff formatter
- `clang-tidy` -> Ruff lint rules
- `gcovr` -> pytest-cov / coverage.py
- C/C++ sanitizers -> mostly not applicable for Python application code; keep tests, warnings, and dependency updates healthy instead

GitHub Actions runs formatting, linting, tests with coverage, and package builds on Python 3.12 and 3.13 across Linux, macOS, and Windows.

This project is licensed under the MIT License.

## Notes

Keep this README updated whenever installation or usage changes.
