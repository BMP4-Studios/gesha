"""Scraper adapter for Hatch Coffee's non-Shopify storefront.

``BaseScraper`` supplies requests and iteration; this class plugs Hatch's
parser module into the registry exposed to the CLI.
"""

from __future__ import annotations

from gesha.coffee_data import CoffeeData
from gesha.parsers.hatch_parser import parse_hatch_collection, parse_hatch_product
from gesha.scrapers.base_scraper import BaseScraper


class HatchScraper(BaseScraper):
    """Retrieve Hatch pages and delegate their unusual payload parsing."""

    BASE_URL = "https://hatchcrafted.com"
    COLLECTION_URL = f"{BASE_URL}/shop"
    SOURCE_NAME = "Hatch"
    ROASTER_NAME = "Hatch Coffee"

    def extract_product_urls(self, html: str) -> list[str]:
        """Find eligible Hatch product links on its shop landing page."""
        return parse_hatch_collection(html, base_url=self.BASE_URL)

    def parse_product(self, html: str, url: str) -> CoffeeData:
        """Convert a Hatch product response into shared catalog data."""
        return parse_hatch_product(html, url)
