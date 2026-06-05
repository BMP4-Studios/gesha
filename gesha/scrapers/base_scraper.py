"""Transport-level scraper workflow shared by every roaster.

We call scrape() in the thread pool, so this is the starting point for all scraping.
Concrete scraper classes provide URL discovery and product parsing while this
base class handles HTTP sessions, failure isolation, and collection iteration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from typing import Any

from gesha.coffee_data import CoffeeData
from curl_cffi.requests import Session


class BaseScraper(ABC):
    """Fetch one roaster's listing and transform its products into DTOs."""

    BASE_URL: str
    COLLECTION_URL: str
    SOURCE_NAME: str
    ROASTER_NAME: str
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",  # Standard browser behavior
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }

    def __init__(self) -> None:
        """Create a browser-like HTTP session used for all requests in a run."""
        # Reuse one impersonated browser session so collection and product
        # requests share headers, cookies, and connection behavior.
        self.session: Session[Any] = Session(impersonate="chrome")
        self.session.headers.update(self.DEFAULT_HEADERS)
        self.logger = logging.getLogger(self.__class__.__module__)

    def scrape(self) -> list[CoffeeData]:
        """Fetch a coffee collection and parse each reachable product into catalog data."""

        # Fetch the collection page; return an empty catalog if the listing fails.
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

        # Each scraper implements its own URL discovery and product parsing.
        product_urls = self.extract_product_urls(response.text)
        coffees: list[CoffeeData] = []

        # Scrape product URLs independently so one bad product does not cancel
        # the rest of the roaster catalog.
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
        """Fetch and parse one product page; returns None on 404."""
        # Treat 404s as normal catalog churn, but surface other HTTP failures.
        response = self.session.get(url, timeout=15)
        if response.status_code == 404:
            return None
        response.raise_for_status()

        # Subclasses implement their own HTML parsing strategy here.
        return self.parse_product(response.text, url)

    @abstractmethod
    def extract_product_urls(self, html: str) -> list[str]:
        """Extract product URLs; implemented for each storefront's markup."""
        raise NotImplementedError

    @abstractmethod
    def parse_product(self, html: str, url: str) -> CoffeeData:
        """Normalize one product page; implemented by source-specific parsers."""
        raise NotImplementedError
