from __future__ import annotations

from typing import List

from gesha.models.coffee import CoffeeData
from gesha.parsers.traffic_parser import parse_traffic_collection, parse_traffic_product
from gesha.scrapers.base import BaseScraper


class TrafficScraper(BaseScraper):
    BASE_URL = "https://www.trafficcoffee.com"
    COLLECTION_URL = f"{BASE_URL}/collections/coffee"
    SOURCE_NAME = "Traffic"
    ROASTER_NAME = "Traffic Coffee"

    def extract_product_urls(self, html: str) -> List[str]:
        return parse_traffic_collection(html, base_url=self.BASE_URL)

    def parse_product(self, html: str, url: str) -> CoffeeData:
        return parse_traffic_product(html, url)
