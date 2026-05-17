"""Scraper registry for Canadian specialty roasters."""

from __future__ import annotations

from typing import TypeAlias

from gesha.scrapers.base import BaseScraper
from gesha.scrapers.demello import DeMelloScraper
from gesha.scrapers.hatch import HatchScraper
from gesha.scrapers.traffic import TrafficScraper

ScraperClass: TypeAlias = type[BaseScraper]

SCRAPER_REGISTRY: dict[str, ScraperClass] = {
    "hatch": HatchScraper,
    "demello": DeMelloScraper,
    "traffic": TrafficScraper,
}


def get_scraper(source: str) -> BaseScraper:
    """Return a scraper instance for a supported source."""
    return SCRAPER_REGISTRY[source]()


def get_scrapers(source: str = "all") -> list[BaseScraper]:
    """Return scraper instances for one source or every supported source."""
    if source == "all":
        return [scraper_class() for scraper_class in SCRAPER_REGISTRY.values()]
    return [get_scraper(source)]


def supported_sources() -> list[str]:
    """Return supported source names, including the aggregate source."""
    return ["all", *SCRAPER_REGISTRY.keys()]
