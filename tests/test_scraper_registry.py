import pytest

from gesha.scrapers import get_scraper, get_scrapers, supported_sources
from gesha.scrapers.demello import DeMelloScraper
from gesha.scrapers.hatch import HatchScraper
from gesha.scrapers.traffic import TrafficScraper


def test_get_scraper_returns_registered_source() -> None:
    assert isinstance(get_scraper("hatch"), HatchScraper)
    assert isinstance(get_scraper("demello"), DeMelloScraper)
    assert isinstance(get_scraper("traffic"), TrafficScraper)
    assert get_scraper("traffic").ROASTER_NAME == "Traffic Coffee"


def test_get_scrapers_returns_all_registered_sources() -> None:
    scrapers = get_scrapers("all")

    assert [type(scraper) for scraper in scrapers] == [
        HatchScraper,
        DeMelloScraper,
        TrafficScraper,
    ]


def test_supported_sources_includes_all_alias() -> None:
    assert supported_sources() == ["all", "hatch", "demello", "traffic"]


def test_get_scraper_rejects_unknown_source() -> None:
    with pytest.raises(KeyError):
        get_scraper("old-coffee-tool-name")
