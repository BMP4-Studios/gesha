"""Tests for the CLI-facing mapping from source names to scraper classes."""

import pytest
from gesha.scrapers import get_scraper, get_scrapers, supported_sources
from gesha.scrapers.shopify_scraper import (
    AngryRoasterScraper,
    ArteryScraper,
    ColorfullScraper,
    DeMelloScraper,
    EthicaScraper,
    HouseOfFunkScraper,
    KohiScraper,
    PorteBleueScraper,
    QuietlyScraper,
    RabbitHoleScraper,
    RogueWaveScraper,
    SubtextScraper,
    TrafficScraper,
)


def test_get_scraper_returns_registered_source() -> None:
    """Each explicit source key instantiates the expected adapter."""
    assert isinstance(get_scraper("demello"), DeMelloScraper)
    assert isinstance(get_scraper("traffic"), TrafficScraper)
    assert isinstance(get_scraper("portebleue"), PorteBleueScraper)
    assert isinstance(get_scraper("colorfull"), ColorfullScraper)
    assert isinstance(get_scraper("angry"), AngryRoasterScraper)
    assert isinstance(get_scraper("houseoffunk"), HouseOfFunkScraper)
    assert isinstance(get_scraper("roguewave"), RogueWaveScraper)
    assert isinstance(get_scraper("quietly"), QuietlyScraper)
    assert isinstance(get_scraper("kohi"), KohiScraper)
    assert isinstance(get_scraper("subtext"), SubtextScraper)
    assert isinstance(get_scraper("artery"), ArteryScraper)
    assert isinstance(get_scraper("ethica"), EthicaScraper)
    assert isinstance(get_scraper("rabbithole"), RabbitHoleScraper)
    assert get_scraper("traffic").ROASTER_NAME == "Traffic Coffee"


def test_get_scrapers_returns_default_sources() -> None:
    """The default refresh retains all currently supported core sources."""
    # Order matters because the default source tuple is the user-facing refresh order.
    scrapers = get_scrapers("all")

    assert [type(scraper) for scraper in scrapers] == [
        DeMelloScraper,
        TrafficScraper,
        PorteBleueScraper,
        ColorfullScraper,
        AngryRoasterScraper,
        HouseOfFunkScraper,
        RogueWaveScraper,
        QuietlyScraper,
        KohiScraper,
        SubtextScraper,
        ArteryScraper,
        EthicaScraper,
        RabbitHoleScraper,
    ]


def test_supported_sources_includes_all_alias() -> None:
    """CLI validation presents aggregate and explicit scraper choices."""
    # ``all`` is a synthetic CLI key and should appear beside concrete roasters.
    assert supported_sources() == [
        "all",
        "demello",
        "traffic",
        "portebleue",
        "colorfull",
        "angry",
        "houseoffunk",
        "roguewave",
        "quietly",
        "kohi",
        "subtext",
        "artery",
        "ethica",
        "rabbithole",
    ]


def test_get_scraper_rejects_unknown_source() -> None:
    """Unknown keys fail instead of silently selecting a different roaster."""
    # Callers validate keys before lookup; direct registry access should stay strict.
    with pytest.raises(KeyError):
        get_scraper("old-coffee-tool-name")
