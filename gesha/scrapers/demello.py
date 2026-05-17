from __future__ import annotations

from typing import List
from urllib.parse import urljoin

import requests

from gesha.models.coffee import CoffeeData
from gesha.parsers.demello_parser import parse_demello_collection, parse_demello_product


class DeMelloScraper:
    BASE_URL = "https://hellodemello.com"
    COLLECTION_URL = f"{BASE_URL}/collections/all-coffee"
    USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36"
    DEFAULT_HEADERS = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)

    def scrape(self) -> List[CoffeeData]:
        response = self.session.get(self.COLLECTION_URL, timeout=15)
        response.raise_for_status()
        product_urls = parse_demello_collection(response.text, base_url=self.BASE_URL)

        coffees: list[CoffeeData] = []
        for product_url in product_urls:
            product_response = self.session.get(product_url, timeout=15)
            if product_response.status_code == 404:
                continue
            product_response.raise_for_status()
            coffee = parse_demello_product(product_response.text, product_url)
            coffees.append(coffee)

        return coffees
