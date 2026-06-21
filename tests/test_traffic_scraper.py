"""Tests for BaseScraper failure isolation through the Traffic adapter."""

from __future__ import annotations

import logging

import requests
from gesha.scrapers import TrafficScraper


class FakeResponse:
    """Minimal response object used to isolate scraper transport behavior."""

    def __init__(
        self,
        text: str,
        status_code: int = 200,
        json_data: dict | None = None,
        headers: dict[str, str] | None = None,
        reason: str = "",
    ) -> None:
        """Create a deterministic response body and HTTP status."""
        self.text = text
        self.status_code = status_code
        self._json_data = json_data
        self.headers = headers or {}
        self.reason = reason

    def raise_for_status(self) -> None:
        """Mirror the HTTP failure behavior the scraper expects from requests."""
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error")

    def json(self) -> dict:
        """Return fixture JSON for Shopify product endpoints."""
        if self._json_data is None:
            raise ValueError("No JSON fixture configured")
        return self._json_data


def test_scrape_skips_failed_traffic_product_urls(monkeypatch) -> None:
    """One failed Traffic product does not discard other parsed products."""
    # The collection exposes one good product and one product that will 404.
    collection_html = (
        '<a href="/collections/coffee/products/test-coffee">Test Coffee</a>'
        '<a href="/collections/coffee/products/bad-page">Bad Page</a>'
    )
    calls = []

    def fake_get(url: str, *args, **kwargs) -> FakeResponse:
        """Return fixture responses for each requested Traffic URL."""
        calls.append(url)

        if url == "https://www.trafficcoffee.com/collections/coffee":
            return FakeResponse(collection_html)
        if url == "https://www.trafficcoffee.com/products/test-coffee":
            return FakeResponse("<html></html>")
        if url == "https://www.trafficcoffee.com/products/test-coffee.js":
            return FakeResponse(
                "",
                json_data={
                    "title": "Test Coffee",
                    "handle": "test-coffee",
                    "price": 2400,
                    "available": True,
                    "type": "coffee",
                    "tags": [],
                    "description": "<p>Origin: Colombia</p><p>In the cup: berry</p>",
                    "variants": [],
                },
            )
        return FakeResponse("", status_code=404)

    scraper = TrafficScraper()
    monkeypatch.setattr(scraper.session, "get", fake_get)

    coffees = scraper.scrape()

    assert len(coffees) == 1
    assert coffees[0].roaster == "Traffic Coffee"
    assert coffees[0].name == "test coffee"
    assert coffees[0].origin == "colombia"
    assert coffees[0].tasting_notes == ["berry"]
    assert "https://www.trafficcoffee.com/products/bad-page.js" in calls


def test_collection_failure_logs_summary_and_full_response(monkeypatch, caplog) -> None:
    """Traffic collection JSON 429s log CLI-sized and full diagnostics."""
    headers = {
        "retry-after": "180",
        "x-request-id": "collection-request-123",
        "cf-ray": "collection-ray-YUL",
        "shopify-complexity-score-v2": "77",
        "set-cookie": "private-cookie=value",
    }

    def fake_get(url: str, *args, **kwargs) -> FakeResponse:
        """Return a detailed 429 from the collection JSON feed."""
        return FakeResponse(
            "<html>rate limited collection</html>",
            status_code=429,
            headers=headers,
            reason="Too Many Requests",
        )

    scraper = TrafficScraper()
    monkeypatch.setattr(scraper.session, "get", fake_get)

    with caplog.at_level(logging.DEBUG):
        coffees = scraper.scrape()

    assert coffees == []
    assert (
        "Failed to fetch Shopify collection JSON for Traffic: HTTP 429 Too Many Requests, Retry-After: 180, "
        "request-id: collection-request-123, cf-ray: collection-ray-YUL, complexity-v2: 77" in caplog.text
    )
    assert "Full HTTP failure while attempting to fetch Shopify collection JSON for Traffic" in caplog.text
    assert "set-cookie: private-cookie=value" in caplog.text
    assert "Body:\n<html>rate limited collection</html>" in caplog.text
