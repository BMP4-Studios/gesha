# Gesha

Gesha is a local-first specialty coffee discovery and cart optimization CLI tool focused on scraping Canadian roasters, normalizing coffee metadata, and storing it in a local SQLite database.

## What it does

- Scrapes specialty coffee products from supported roasters
- Normalizes roaster, origin, process, tasting notes, price, bag size, and availability
- Stores coffee records locally in SQLite
- Provides CLI commands to query and inspect coffees

## Install

Create and activate a Python virtual environment, then install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Optionally install the package in editable mode so the `gesha` CLI is available directly:

```bash
python -m pip install -e .
```

## Initialize the database

```bash
gesha init
```

This creates the SQLite schema for roasters, coffees, and tasting notes.

`gesha scrape` will now automatically initialize the database schema if needed.

## Requirements

- Internet access is required for scraping remote roaster pages.
- If `gesha scrape` fails with a DNS or network error, verify your connection and retry.

## Basic usage

Scrape Hatch Coffee:

```bash
gesha scrape hatch
```

Scrape De Mello Coffee:

```bash
gesha scrape demello
```

Scrape Traffic Coffee:

```bash
gesha scrape traffic
```

Scrape all supported roasters (default):

```bash
gesha scrape
```

After scraping, the CLI will automatically display the newly imported coffees.

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

## Notes

Keep this README updated whenever installation or usage changes.
