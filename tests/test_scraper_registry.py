"""Tests for the CLI-facing mapping from source names to scraper classes."""

import pytest

from gesha.scrapers import get_scraper, get_scrapers, supported_sources
from gesha.scrapers.hatch import HatchScraper
from gesha.scrapers.shopify import AngryRoasterScraper, ColorfullScraper, PorteBleueScraper, DeMelloScraper, TrafficScraper


def test_get_scraper_returns_registered_source() -> None:
    """Each explicit source key instantiates the expected adapter."""
    assert isinstance(get_scraper("hatch"), HatchScraper)
    assert isinstance(get_scraper("demello"), DeMelloScraper)
    assert isinstance(get_scraper("traffic"), TrafficScraper)
    assert isinstance(get_scraper("portebleue"), PorteBleueScraper)
    assert isinstance(get_scraper("colorfull"), ColorfullScraper)
    assert isinstance(get_scraper("angry"), AngryRoasterScraper)
    assert get_scraper("traffic").ROASTER_NAME == "Traffic Coffee"


def test_get_scrapers_returns_default_sources_without_hatch() -> None:
    """The default refresh excludes opt-in Hatch while retaining core sources."""
    scrapers = get_scrapers("all")

    assert [type(scraper) for scraper in scrapers] == [
        DeMelloScraper,
        TrafficScraper,
        PorteBleueScraper,
        ColorfullScraper,
        AngryRoasterScraper,
    ]


def test_supported_sources_includes_all_alias_and_explicit_hatch() -> None:
    """CLI validation presents aggregate and explicit scraper choices."""
    assert supported_sources() == ["all", "hatch", "demello", "traffic", "portebleue", "colorfull", "angry"]


def test_get_scraper_rejects_unknown_source() -> None:
    """Unknown keys fail instead of silently selecting a different roaster."""
    with pytest.raises(KeyError):
        get_scraper("old-coffee-tool-name")
