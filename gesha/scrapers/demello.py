from __future__ import annotations

from typing import List

from gesha.models.coffee import CoffeeData
from gesha.parsers.demello_parser import parse_demello_collection, parse_demello_product
from gesha.scrapers.base import BaseScraper


class DeMelloScraper(BaseScraper):
    BASE_URL = "https://hellodemello.com"
    COLLECTION_URL = f"{BASE_URL}/collections/all-coffee"
    SOURCE_NAME = "De Mello"
    ROASTER_NAME = "De Mello Coffee"

    def extract_product_urls(self, html: str) -> List[str]:
        return parse_demello_collection(html, base_url=self.BASE_URL)

    def parse_product(self, html: str, url: str) -> CoffeeData:
        return parse_demello_product(html, url)
