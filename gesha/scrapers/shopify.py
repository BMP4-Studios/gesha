from __future__ import annotations

import re
from typing import Any, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from gesha.models.coffee import CoffeeData
from gesha.normalization.normalize import normalize_country, normalize_process, normalize_tasting_notes
from gesha.parsers.common import clean_tasting_note_candidates, extract_labeled_value
from gesha.scrapers.base import BaseScraper


SHOPIFY_DETAIL_LABELS = [
    "Country",
    "Origin",
    "Region",
    "Place",
    "Producer",
    "Producers",
    "Coffee Producers",
    "Farm",
    "Variety",
    "Varieties",
    "Cultivar",
    "Process",
    "Method",
    "Altitude",
    "Elevation",
    "Notes",
    "Tasting Notes",
    "In the cup",
    "Amount",
    "Size",
    "Specs",
]


class ShopifyScraper(BaseScraper):
    COLLECTION_PATH = "/collections/coffee"
    PRODUCT_URL_PATTERN = re.compile(r"^/(?:collections/[^/]+/)?products/[^/?#]+$")
    INCLUDE_PRODUCT_TYPES: tuple[str, ...] = ()
    INCLUDE_TAGS: tuple[str, ...] = ("coffee",)
    EXCLUDE_HANDLE_KEYWORDS: tuple[str, ...] = ()

    def extract_product_urls(self, html: str) -> List[str]:
        soup = BeautifulSoup(html, "html.parser")
        urls: list[str] = []
        for anchor in soup.select("a[href*='/products/']"):
            href = anchor.get("href", "").split("?", 1)[0].strip()
            if not self.PRODUCT_URL_PATTERN.match(href):
                continue
            urls.append(self._canonical_product_url(urljoin(self.BASE_URL, href)))
        return sorted(dict.fromkeys(urls))

    def scrape(self) -> List[CoffeeData]:
        response = self.session.get(self.COLLECTION_URL, timeout=15)
        response.raise_for_status()
        product_urls = self.extract_product_urls(response.text)
        coffees: list[CoffeeData] = []

        for product_url in product_urls:
            try:
                product_response = self.session.get(f"{product_url}.js", timeout=15)
                if product_response.status_code == 404:
                    continue
                product_response.raise_for_status()
                product_data = product_response.json()
            except (requests.exceptions.RequestException, ValueError) as exc:
                self.logger.warning("Skipping %s product JSON because it failed: %s (%s)", self.SOURCE_NAME, product_url, exc)
                continue

            if not self._is_coffee_product(product_data):
                continue

            try:
                coffees.append(self._coffee_from_product(product_data, product_url))
            except Exception as exc:
                self.logger.warning("Skipping %s product JSON because parsing failed: %s (%s)", self.SOURCE_NAME, product_url, exc)

        return coffees

    def parse_product(self, html: str, url: str) -> CoffeeData:
        raise NotImplementedError("ShopifyScraper parses product JSON instead of product HTML.")

    def _canonical_product_url(self, url: str) -> str:
        parsed = urlparse(url)
        handle = parsed.path.rstrip("/").rsplit("/", 1)[-1]
        return urljoin(self.BASE_URL, f"/products/{handle}")

    def _is_coffee_product(self, product_data: dict[str, Any]) -> bool:
        handle = str(product_data.get("handle") or "").lower()
        if any(keyword in handle for keyword in self.EXCLUDE_HANDLE_KEYWORDS):
            return False

        product_type = str(product_data.get("type") or "").strip().lower()
        tags = {str(tag).strip().lower() for tag in product_data.get("tags") or []}

        if self.INCLUDE_PRODUCT_TYPES and product_type in {value.lower() for value in self.INCLUDE_PRODUCT_TYPES}:
            return True
        if self.INCLUDE_TAGS and tags.intersection({value.lower() for value in self.INCLUDE_TAGS}):
            return True
        return not self.INCLUDE_PRODUCT_TYPES and not self.INCLUDE_TAGS

    def _coffee_from_product(self, product_data: dict[str, Any], url: str) -> CoffeeData:
        description = self._description_text(product_data)
        details = self._extract_details(description)

        return CoffeeData(
            roaster=self.ROASTER_NAME,
            name=str(product_data.get("title") or "Unknown coffee"),
            origin=normalize_country(details.get("origin")),
            producer=details.get("producer"),
            process=normalize_process(details.get("process")),
            varietal=details.get("varietal"),
            altitude=details.get("altitude"),
            tasting_notes=self._extract_tasting_notes(description),
            roast_style=self._extract_roast_style(product_data),
            price_cents=self._extract_price(product_data),
            bag_size=details.get("bag_size") or self._extract_bag_size(product_data),
            url=url,
            availability=bool(product_data.get("available", True)),
        )

    def _description_text(self, product_data: dict[str, Any]) -> str:
        html = str(product_data.get("description") or "")
        return BeautifulSoup(html, "html.parser").get_text("\n", strip=True)

    def _extract_details(self, description: str) -> dict[str, Optional[str]]:
        return {
            "origin": extract_labeled_value(description, ["Origin", "Country", "Region"], SHOPIFY_DETAIL_LABELS),
            "producer": extract_labeled_value(description, ["Coffee Producers", "Producer", "Producers"], SHOPIFY_DETAIL_LABELS),
            "process": extract_labeled_value(description, ["Process", "Method"], SHOPIFY_DETAIL_LABELS),
            "varietal": extract_labeled_value(description, ["Variety", "Varieties", "Cultivar"], SHOPIFY_DETAIL_LABELS),
            "altitude": extract_labeled_value(description, ["Altitude", "Elevation"], SHOPIFY_DETAIL_LABELS),
            "bag_size": extract_labeled_value(description, ["Amount", "Size"], SHOPIFY_DETAIL_LABELS),
        }

    def _extract_tasting_notes(self, description: str) -> list[str]:
        value = extract_labeled_value(description, ["Tasting Notes", "Notes", "In the cup"], SHOPIFY_DETAIL_LABELS)
        if not value:
            for pattern in (
                r"in the cup (?:you can find|you'll find|is|are)?\s*(.+?)(?:\.|$)",
                r"(?:notes of|profile of)\s+(.+?)(?:\.|$)",
            ):
                match = re.search(pattern, description, re.IGNORECASE | re.DOTALL)
                if match:
                    value = match.group(1)
                    break
        if not value:
            return []
        parts = re.split(r"[,;/]|&|\s+-\s+", value)
        return normalize_tasting_notes(clean_tasting_note_candidates(parts))

    def _extract_roast_style(self, product_data: dict[str, Any]) -> Optional[str]:
        tags = {str(tag).strip().lower() for tag in product_data.get("tags") or []}
        styles = [style for style in ("filter", "espresso") if style in tags]
        return ", ".join(styles) if styles else None

    def _extract_price(self, product_data: dict[str, Any]) -> Optional[int]:
        price = product_data.get("price")
        return int(price) if isinstance(price, int) else None

    def _extract_bag_size(self, product_data: dict[str, Any]) -> Optional[str]:
        for variant in product_data.get("variants") or []:
            title = str(variant.get("title") or "")
            match = re.search(r"\b\d+\s*(?:g|kg|oz|lb)\b", title, re.IGNORECASE)
            if match:
                return match.group(0)
        return None


class PorteBleueScraper(ShopifyScraper):
    BASE_URL = "https://portebleue.ca"
    COLLECTION_URL = f"{BASE_URL}/collections/coffee"
    SOURCE_NAME = "Porte Bleue"
    ROASTER_NAME = "Porte Bleue"
    INCLUDE_PRODUCT_TYPES = ("bag",)


class ColorfullScraper(ShopifyScraper):
    BASE_URL = "https://colorfullcoffee.com"
    COLLECTION_URL = f"{BASE_URL}/collections/all"
    SOURCE_NAME = "Colorfull"
    ROASTER_NAME = "Colorfull Coffee"
    INCLUDE_TAGS = ()
    EXCLUDE_HANDLE_KEYWORDS = ("gift", "subscription")


class AngryRoasterScraper(ShopifyScraper):
    BASE_URL = "https://theangryroaster.com"
    COLLECTION_URL = f"{BASE_URL}/collections/coffee"
    SOURCE_NAME = "The Angry Roaster"
    ROASTER_NAME = "The Angry Roaster"
    INCLUDE_PRODUCT_TYPES = ("coffee",)
