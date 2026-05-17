from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from typing import List

import requests

from gesha.models.coffee import CoffeeData


class BaseScraper(ABC):
    BASE_URL: str
    COLLECTION_URL: str
    SOURCE_NAME: str
    ROASTER_NAME: str
    USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36"
    DEFAULT_HEADERS = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)
        self.logger = logging.getLogger(self.__class__.__module__)

    def scrape(self) -> List[CoffeeData]:
        """Fetch a collection page, fetch each product page, and return normalized data."""
        response = self.session.get(self.COLLECTION_URL, timeout=15)
        response.raise_for_status()
        product_urls = self.extract_product_urls(response.text)
        coffees: list[CoffeeData] = []

        for product_url in product_urls:
            try:
                product_response = self.session.get(product_url, timeout=15)
                if product_response.status_code == 404:
                    continue
                product_response.raise_for_status()
            except requests.exceptions.RequestException as exc:
                self.logger.warning(
                    "Skipping %s product URL because it failed: %s (%s)",
                    self.SOURCE_NAME,
                    product_url,
                    exc,
                )
                continue

            try:
                coffee = self.parse_product(product_response.text, product_url)
            except Exception as exc:
                self.logger.warning(
                    "Skipping %s product URL because parsing failed: %s (%s)",
                    self.SOURCE_NAME,
                    product_url,
                    exc,
                )
                continue

            coffees.append(coffee)

        return coffees

    @abstractmethod
    def extract_product_urls(self, html: str) -> List[str]:
        """Extract absolute product URLs from collection HTML."""
        raise NotImplementedError

    @abstractmethod
    def parse_product(self, html: str, url: str) -> CoffeeData:
        """Normalize one product page into CoffeeData."""
        raise NotImplementedError
