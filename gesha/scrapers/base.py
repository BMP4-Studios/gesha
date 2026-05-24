from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from typing import Any

from gesha.models.coffee import CoffeeData
from curl_cffi.requests import Session


class BaseScraper(ABC):
    BASE_URL: str
    COLLECTION_URL: str
    SOURCE_NAME: str
    ROASTER_NAME: str
    # Use a common Windows Chrome User-Agent to avoid being blocked on Windows
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    DEFAULT_HEADERS = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive", # Standard browser behavior
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }

    def __init__(self) -> None:
        self.session: Session[Any] = Session(impersonate="chrome")
        self.session.headers.update(self.DEFAULT_HEADERS)
        self.logger = logging.getLogger(self.__class__.__module__)

    def scrape(self) -> list[CoffeeData]:
        """Fetch a collection page, fetch each product page, and return normalized data."""
        try:
            response = self.session.get(self.COLLECTION_URL, timeout=15)
            response.raise_for_status()
        except Exception as exc:
            self.logger.warning(
                "Failed to fetch collection for %s: %s",
                self.SOURCE_NAME,
                exc,
            )
            return []

        product_urls = self.extract_product_urls(response.text)
        coffees: list[CoffeeData] = []

        for product_url in product_urls:
            try:
                coffee = self.scrape_product(product_url)
                if coffee:
                    coffees.append(coffee)
            except Exception as exc:
                self.logger.warning(
                    "Skipping %s product URL because processing failed: %s (%s)",
                    self.SOURCE_NAME,
                    product_url,
                    exc,
                )
        return coffees

    def scrape_product(self, url: str) -> CoffeeData | None:
        """Fetch and parse a single product URL. Defaults to HTML-based parsing."""
        response = self.session.get(url, timeout=15)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return self.parse_product(response.text, url)

    @abstractmethod
    def extract_product_urls(self, html: str) -> list[str]:
        """Extract absolute product URLs from collection HTML."""
        raise NotImplementedError

    @abstractmethod
    def parse_product(self, html: str, url: str) -> CoffeeData:
        """Normalize one product page into CoffeeData."""
        raise NotImplementedError
