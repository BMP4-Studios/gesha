"""Scraper registry for Canadian specialty roasters."""

from __future__ import annotations

from typing import TypeAlias

from gesha.scrapers.base_scraper import BaseScraper
from gesha.scrapers.shopify_scraper import (
    AngryRoasterScraper,
    ColorfullScraper,
    DeMelloScraper,
    PorteBleueScraper,
    TrafficScraper,
)

ScraperClass: TypeAlias = type[BaseScraper]

# Source keys are the public CLI contract for ``gesha scrape <source>``.
SCRAPER_REGISTRY: dict[str, ScraperClass] = {
    "demello": DeMelloScraper,
    "traffic": TrafficScraper,
    "portebleue": PorteBleueScraper,
    "colorfull": ColorfullScraper,
    "angry": AngryRoasterScraper,
}

# ``all`` intentionally follows this tuple so default output order is stable.
DEFAULT_SOURCES = (
    "demello",
    "traffic",
    "portebleue",
    "colorfull",
    "angry",
)


def get_scraper(source: str) -> BaseScraper:
    """Instantiate one named scraper for ``gesha scrape <source>``."""
    # Registry lookup is intentionally direct; callers validate supported keys first.
    return SCRAPER_REGISTRY[source]()


def get_scrapers(source: str = "all") -> list[BaseScraper]:
    """Instantiate explicit or default scrapers for the CLI refresh workflow."""
    # ``all`` expands to the configured default order. A single source still
    # returns a list so the CLI can use one scrape loop for both cases.
    if source == "all":
        return [SCRAPER_REGISTRY[name]() for name in DEFAULT_SOURCES]
    return [get_scraper(source)]


def supported_sources() -> list[str]:
    """Return accepted CLI source keys, including the aggregate ``all`` key."""
    # Typer commands use this for validation and user-facing error messages.
    return ["all", *SCRAPER_REGISTRY.keys()]
