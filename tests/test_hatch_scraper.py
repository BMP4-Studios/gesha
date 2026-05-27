"""Tests for BaseScraper failure isolation through the Hatch adapter."""

from __future__ import annotations

import requests

from gesha.coffee_data import CoffeeData
from gesha.scrapers.hatch_scraper import HatchScraper


class FakeResponse:
    """Minimal response object used to isolate scraper transport behavior."""

    def __init__(self, text: str, status_code: int = 200) -> None:
        """Create a deterministic response body and HTTP status."""
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        """Mirror the HTTP failure behavior the scraper expects from requests."""
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error")


def test_scrape_skips_failed_product_urls(monkeypatch) -> None:
    """One failed Hatch product does not discard successfully parsed products."""
    collection_html = '<a href="/shop/test-coffee">Test Coffee</a><a href="/shop/bad-page">Bad Page</a>'
    good_coffee = CoffeeData(
        roaster="Hatch Coffee",
        name="Test Coffee",
        origin="Colombia",
        tasting_notes=["berry"],
        url="https://hatchcrafted.com/shop/test-coffee",
    )

    calls = []

    def fake_get(url: str, timeout: int) -> FakeResponse:
        """Return fixture responses for each requested Hatch URL."""
        calls.append(url)
        if url == "https://hatchcrafted.com/shop":
            return FakeResponse(collection_html)
        if url == "https://hatchcrafted.com/shop/test-coffee":
            return FakeResponse("<html></html>")
        return FakeResponse("", status_code=404)

    def fake_parse(html: str, url: str) -> CoffeeData:
        """Stand in for product parsing while exercising scraper iteration."""
        assert url == "https://hatchcrafted.com/shop/test-coffee"
        return good_coffee

    scraper = HatchScraper()
    monkeypatch.setattr(scraper.session, "get", lambda url, timeout: fake_get(url, timeout))
    monkeypatch.setattr("gesha.scrapers.hatch.parse_hatch_product", fake_parse)

    coffees = scraper.scrape()

    assert coffees == [good_coffee]
    assert "https://hatchcrafted.com/shop/bad-page" in calls
