import pytest
from gesha.scrapers import get_scraper, get_scrapers, supported_sources
from gesha.scrapers.demello import DeMelloScraper
from gesha.scrapers.hatch import HatchScraper
from gesha.scrapers.shopify import (
    AngryRoasterScraper,
    ColorfullScraper,
    HouseOfFunkScraper,
    PorteBleueScraper,
    RogueWaveScraper,
)
from gesha.scrapers.traffic import TrafficScraper


def test_get_scraper_returns_registered_source() -> None:
    assert isinstance(get_scraper("hatch"), HatchScraper)
    assert isinstance(get_scraper("demello"), DeMelloScraper)
    assert isinstance(get_scraper("traffic"), TrafficScraper)
    assert isinstance(get_scraper("portebleue"), PorteBleueScraper)
    assert isinstance(get_scraper("colorfull"), ColorfullScraper)
    assert isinstance(get_scraper("angry"), AngryRoasterScraper)
    assert isinstance(get_scraper("roguewave"), RogueWaveScraper)
    assert isinstance(get_scraper("houseoffunk"), HouseOfFunkScraper)
    assert get_scraper("traffic").ROASTER_NAME == "Traffic Coffee"


def test_get_scrapers_returns_default_sources_without_hatch() -> None:
    scrapers = get_scrapers("all")

    assert [type(scraper) for scraper in scrapers] == [
        DeMelloScraper,
        TrafficScraper,
        PorteBleueScraper,
        ColorfullScraper,
        AngryRoasterScraper,
        RogueWaveScraper,
        HouseOfFunkScraper,
    ]


def test_supported_sources_includes_all_alias_and_explicit_hatch() -> None:
    assert supported_sources() == [
        "all",
        "hatch",
        "demello",
        "traffic",
        "portebleue",
        "colorfull",
        "angry",
        "roguewave",
        "houseoffunk",
    ]


def test_get_scraper_rejects_unknown_source() -> None:
    with pytest.raises(KeyError):
        get_scraper("old-coffee-tool-name")
