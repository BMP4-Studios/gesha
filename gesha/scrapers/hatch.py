from __future__ import annotations

from gesha.models.coffee import CoffeeData
from gesha.parsers.hatch_parser import parse_hatch_collection, parse_hatch_product
from gesha.scrapers.base import BaseScraper


class HatchScraper(BaseScraper):
    BASE_URL = "https://hatchcrafted.com"
    COLLECTION_URL = f"{BASE_URL}/shop"
    SOURCE_NAME = "Hatch"
    ROASTER_NAME = "Hatch Coffee"

    def extract_product_urls(self, html: str) -> list[str]:
        return parse_hatch_collection(html, base_url=self.BASE_URL)

    def parse_product(self, html: str, url: str) -> CoffeeData:
        return parse_hatch_product(html, url)
