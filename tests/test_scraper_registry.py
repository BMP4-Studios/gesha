"""Tests for the CLI-facing mapping from source names to scraper classes."""

import pytest
from gesha.scrapers import DEFAULT_SOURCES, SCRAPER_REGISTRY, get_scraper, get_scrapers, supported_sources
from gesha.scrapers.shopify_children_scrapers import (
    AngryRoasterScraper,
    ArteryScraper,
    CafePistaScraper,
    Celcius94Scraper,
    ColorfullScraper,
    DeMelloScraper,
    EscapeScraper,
    EthicaScraper,
    HouseOfFunkScraper,
    JungleScraper,
    KohiScraper,
    MonogramScraper,
    NarvalScraper,
    NektarScraper,
    NucleusScraper,
    PiratesScraper,
    PorteBleueScraper,
    QuietlyScraper,
    RabbitHoleScraper,
    RogueWaveScraper,
    SeptemberScraper,
    SipstruckScraper,
    SubtextScraper,
    TrafficScraper,
    ZaAndKloScraper,
)


def test_get_scraper_returns_registered_source() -> None:
    """Each explicit source key instantiates the expected adapter."""
    assert isinstance(get_scraper("angry"), AngryRoasterScraper)
    assert isinstance(get_scraper("artery"), ArteryScraper)
    assert isinstance(get_scraper("cafepista"), CafePistaScraper)
    assert isinstance(get_scraper("94celcius"), Celcius94Scraper)
    assert isinstance(get_scraper("colorfull"), ColorfullScraper)
    assert isinstance(get_scraper("demello"), DeMelloScraper)
    assert isinstance(get_scraper("escape"), EscapeScraper)
    assert isinstance(get_scraper("ethica"), EthicaScraper)
    assert isinstance(get_scraper("houseoffunk"), HouseOfFunkScraper)
    assert isinstance(get_scraper("jungle"), JungleScraper)
    assert isinstance(get_scraper("kohi"), KohiScraper)
    assert isinstance(get_scraper("monogram"), MonogramScraper)
    assert isinstance(get_scraper("nucleus"), NucleusScraper)
    assert isinstance(get_scraper("narval"), NarvalScraper)
    assert isinstance(get_scraper("nektar"), NektarScraper)
    assert isinstance(get_scraper("pirates"), PiratesScraper)
    assert isinstance(get_scraper("portebleue"), PorteBleueScraper)
    assert isinstance(get_scraper("quietly"), QuietlyScraper)
    assert isinstance(get_scraper("rabbithole"), RabbitHoleScraper)
    assert isinstance(get_scraper("roguewave"), RogueWaveScraper)
    assert isinstance(get_scraper("september"), SeptemberScraper)
    assert isinstance(get_scraper("sipstruck"), SipstruckScraper)
    assert isinstance(get_scraper("subtext"), SubtextScraper)
    assert isinstance(get_scraper("traffic"), TrafficScraper)
    assert isinstance(get_scraper("zaandklo"), ZaAndKloScraper)


def test_get_scrapers_returns_default_sources() -> None:
    """The default refresh retains all currently supported core sources."""
    # Order matters because the default source tuple is the user-facing refresh order.
    scrapers = get_scrapers("all")

    assert [type(scraper) for scraper in scrapers] == [SCRAPER_REGISTRY[name] for name in DEFAULT_SOURCES]


def test_supported_sources_includes_all_alias() -> None:
    """CLI validation presents aggregate and explicit scraper choices."""
    # ``all`` is a synthetic CLI key and should appear beside concrete roasters.
    assert supported_sources() == ["all", *DEFAULT_SOURCES]


def test_get_scraper_rejects_unknown_source() -> None:
    """Unknown keys fail instead of silently selecting a different roaster."""
    # Callers validate keys before lookup; direct registry access should stay strict.
    with pytest.raises(KeyError):
        get_scraper("old-coffee-tool-name")
