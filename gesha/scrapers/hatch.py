from __future__ import annotations

from typing import List

import requests

from gesha.models.coffee import CoffeeData
from gesha.parsers.hatch_parser import parse_hatch_collection, parse_hatch_product


class HatchScraper:
    BASE_URL = "https://hatchcrafted.com"
    COLLECTION_URL = f"{BASE_URL}/shop"
    USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.USER_AGENT})

    def scrape(self) -> List[CoffeeData]:
        response = self.session.get(self.COLLECTION_URL, timeout=15)
        response.raise_for_status()
        product_urls = parse_hatch_collection(response.text, base_url=self.BASE_URL)
        coffees: list[CoffeeData] = []
        for product_url in product_urls:
            product_response = self.session.get(product_url, timeout=15)
            product_response.raise_for_status()
            coffee = parse_hatch_product(product_response.text, product_url)
            coffees.append(coffee)
        return coffees
