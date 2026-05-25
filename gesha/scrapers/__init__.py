"""Scraper registry for Canadian specialty roasters."""

from __future__ import annotations

from typing import TypeAlias

from gesha.scrapers.base import BaseScraper
from gesha.scrapers.hatch import HatchScraper
from gesha.scrapers.shopify import (
    AngryRoasterScraper,
    ColorfullScraper,
    PorteBleueScraper,
    DeMelloScraper,
    TrafficScraper,
)

ScraperClass: TypeAlias = type[BaseScraper]

SCRAPER_REGISTRY: dict[str, ScraperClass] = {
    "hatch": HatchScraper,
    "demello": DeMelloScraper,
    "traffic": TrafficScraper,
    "portebleue": PorteBleueScraper,
    "colorfull": ColorfullScraper,
    "angry": AngryRoasterScraper,
}

DEFAULT_SOURCES = (
    "demello",
    "traffic",
    "portebleue",
    "colorfull",
    "angry",
)


def get_scraper(source: str) -> BaseScraper:
    """Instantiate one named scraper for ``gesha scrape <source>``."""
    return SCRAPER_REGISTRY[source]()


def get_scrapers(source: str = "all") -> list[BaseScraper]:
    """Instantiate explicit or default scrapers for the CLI refresh workflow."""
    if source == "all":
        return [SCRAPER_REGISTRY[name]() for name in DEFAULT_SOURCES]
    return [get_scraper(source)]


def supported_sources() -> list[str]:
    """Return accepted CLI source keys, including the aggregate ``all`` key."""
    return ["all", *SCRAPER_REGISTRY.keys()]
