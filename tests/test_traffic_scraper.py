from __future__ import annotations

import requests

from gesha.models.coffee import CoffeeData
from gesha.scrapers import TrafficScraper


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error")


def test_scrape_skips_failed_traffic_product_urls(monkeypatch) -> None:
    collection_html = (
        '<a href="/collections/coffee/products/test-coffee">Test Coffee</a>'
        '<a href="/collections/coffee/products/bad-page">Bad Page</a>'
    )
    good_coffee = CoffeeData(
        roaster="Traffic Coffee",
        name="Test Coffee",
        origin="Colombia",
        tasting_notes=["berry"],
        url="https://www.trafficcoffee.com/collections/coffee/products/test-coffee",
    )

    calls = []

    def fake_get(url: str, timeout: int) -> FakeResponse:
        calls.append(url)
        if url == "https://www.trafficcoffee.com/collections/coffee":
            return FakeResponse(collection_html)
        if url == "https://www.trafficcoffee.com/collections/coffee/products/test-coffee":
            return FakeResponse("<html></html>")
        return FakeResponse("", status_code=404)

    def fake_parse(html: str, url: str) -> CoffeeData:
        assert url == "https://www.trafficcoffee.com/collections/coffee/products/test-coffee"
        return good_coffee

    scraper = TrafficScraper()
    monkeypatch.setattr(scraper.session, "get", lambda url, timeout: fake_get(url, timeout))
    monkeypatch.setattr("gesha.scrapers.shopify.parse_traffic_product", fake_parse)

    coffees = scraper.scrape()

    assert coffees == [good_coffee]
    assert "https://www.trafficcoffee.com/collections/coffee/products/bad-page" in calls
