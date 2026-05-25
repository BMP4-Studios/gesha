# Gesha

<img src="assets/logo.png" alt="Gesha Logo" width="300">

Gesha is a local-first specialty coffee discovery and cart optimization CLI tool focused on scraping Canadian roasters, normalizing coffee metadata, and storing it in a local SQLite database.

## What it does

- Scrapes specialty coffee products from supported roasters
- Normalizes roaster, origin, process, tasting notes, price, bag size, and availability
- Stores coffee records locally in SQLite
- Provides CLI commands to query and inspect coffees

## Install

Create and activate a Python virtual environment, then install dependencies.

**macOS/Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (Git Bash):**

```bash
python -m venv .venv
source .venv/Scripts/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Optionally install the package in editable mode so the `gesha` CLI is available directly:

```bash
python -m pip install -e .
```

## Requirements

- Internet access is required for scraping remote roaster pages.
- If `gesha` fails with a DNS or network error, verify your connection and retry.

## Basic usage

- Refresh every supported roaster, remove stale local rows, and list the cleaned catalog: `gesha`
- Scrape all supported roasters: `gesha scrape`
- Scrape a single supported roaster: `gesha scrape traffic`
- List coffees that were already scraped: `gesha list`
- Filter by process: `gesha list --process washed`
- Filter by tasting note: `gesha list --flavour berry`
- Show a coffee by ID: `gesha show 1`
- Run tests: `python -m pytest`
