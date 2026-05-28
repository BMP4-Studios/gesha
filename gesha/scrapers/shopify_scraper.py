"""Shopify-oriented scraping and adapters for several supported roasters.

The generic ``ShopifyScraper`` reads product-page label/value sections first
and uses Shopify JSON as support data for price, variants, availability, and
fallback description metadata.
"""

from __future__ import annotations

import re
from typing import Any, cast
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from gesha.coffee_data import CoffeeData
from gesha.normalization import normalize_country, normalize_process, normalize_tasting_notes, remove_emojis
from gesha.parsers.common import (
    DEFAULT_PRODUCT_FACT_LABELS,
    DEFAULT_PRODUCT_FACT_STOP_LABELS,
    extract_labeled_product_facts_from_html,
    extract_labeled_product_facts_from_text,
)
from gesha.scrapers.base_scraper import BaseScraper


class ShopifyScraper(BaseScraper):
    """Extract coffee products from stores exposing Shopify product JSON."""

    PRODUCT_URL_PATTERN = re.compile(r"^/(?:collections/[^/]+/)?products/[^/?#]+$")
    PRODUCT_LINK_ATTRIBUTES: tuple[str, ...] = ("href", "data-url")
    INCLUDE_TAGS: tuple[str, ...] = ("coffee",)
    EXCLUDE_HANDLE_KEYWORDS: tuple[str, ...] = ("subscription", "sub", "gift", "recurring")
    PRODUCT_FACT_LABELS = DEFAULT_PRODUCT_FACT_LABELS
    PRODUCT_FACT_STOP_LABELS = DEFAULT_PRODUCT_FACT_STOP_LABELS
    PRODUCT_FACT_SELECTORS: tuple[str, ...] = ()

    def extract_product_urls(self, html: str) -> list[str]:
        """Convert collection product links into canonical Shopify product URLs."""
        soup = BeautifulSoup(html, "html.parser")
        urls: list[str] = []
        for element in soup.select("a[href*='/products/'], [data-url*='/products/']"):
            for attribute in self.PRODUCT_LINK_ATTRIBUTES:
                raw_href = element.get(attribute)
                if not isinstance(raw_href, str):
                    continue
                href = raw_href.split("?", 1)[0].strip()
                path = urlparse(href).path if href.startswith(("http://", "https://")) else href
                if not self.PRODUCT_URL_PATTERN.match(path):
                    continue

                handle = path.rstrip("/").rsplit("/", 1)[-1].lower()
                if self._is_excluded_handle(handle):
                    continue

                urls.append(self._canonical_product_url(urljoin(self.BASE_URL, href)))
        return sorted(dict.fromkeys(urls))

    def scrape_product(self, url: str) -> CoffeeData | None:
        """Fetch Shopify HTML first, then JSON support data for one product."""
        html_soup: BeautifulSoup | None = None
        html_facts: dict[str, str] = {}
        res_html = self.session.get(url, timeout=15)
        if res_html.status_code == 200:
            html_soup = BeautifulSoup(res_html.text, "html.parser")
            html_facts = self._extract_html_product_facts(html_soup)

        session = cast(Any, self.session)
        headers = session.headers.copy()
        headers["Referer"] = url
        response = session.get(f"{url}.js", headers=headers, timeout=15)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        product_data = cast(dict[str, Any], response.json())

        if not self._is_coffee_product(product_data):
            return None

        return self._coffee_from_product(product_data, url, html_soup=html_soup, html_facts=html_facts)

    def parse_product(self, html: str, url: str) -> CoffeeData:
        """Prevent the base HTML parser path for JSON-driven Shopify products."""
        raise NotImplementedError("ShopifyScraper parses product JSON instead of product HTML.")

    def _canonical_product_url(self, url: str) -> str:
        """Strip collection prefixes so one Shopify item has one stored URL."""
        parsed = urlparse(url)
        handle = parsed.path.rstrip("/").rsplit("/", 1)[-1]
        return urljoin(self.BASE_URL, f"/products/{handle}")

    def _normalize_tags(self, product_data: dict[str, Any]) -> set[str]:
        """Return lowercase Shopify tags independent of API string/list shape."""
        raw_tags = product_data.get("tags") or []
        if isinstance(raw_tags, str):
            raw_tags = [tag.strip() for tag in raw_tags.split(",") if tag.strip()]
        return {str(tag).strip().lower() for tag in raw_tags if str(tag).strip()}

    def _is_excluded_handle(self, handle: str) -> bool:
        """Return whether a product handle belongs to a non-catalog item."""
        return any(keyword in handle for keyword in self.EXCLUDE_HANDLE_KEYWORDS)

    def _is_coffee_product(self, product_data: dict[str, Any]) -> bool:
        """Reject subscriptions and accept products satisfying source tag rules."""
        handle = str(product_data.get("handle") or "").lower()
        tags = self._normalize_tags(product_data)

        if self._is_excluded_handle(handle) or any(keyword in tags for keyword in self.EXCLUDE_HANDLE_KEYWORDS):
            return False

        if self.INCLUDE_TAGS and tags.intersection({value.lower() for value in self.INCLUDE_TAGS}):
            return True

        return not self.INCLUDE_TAGS

    def _coffee_from_product(
        self,
        product_data: dict[str, Any],
        url: str,
        html_soup: BeautifulSoup | None = None,
        html_facts: dict[str, str] | None = None,
    ) -> CoffeeData:
        """Merge product-page facts, Shopify JSON, and title fallbacks."""
        description = self._description_text(product_data)
        json_facts = self._extract_details(description)
        page_facts = html_facts or (self._extract_html_product_facts(html_soup) if html_soup else {})
        title = remove_emojis(str(product_data.get("title") or "Unknown coffee"))
        title_facts = self._extract_details_from_title(title)

        origin = page_facts.get("origin") or json_facts.get("origin") or title_facts.get("origin") or title
        producer = page_facts.get("producer") or json_facts.get("producer")
        process = page_facts.get("process") or json_facts.get("process") or title_facts.get("process")
        varietal = page_facts.get("varietal") or json_facts.get("varietal")
        altitude = page_facts.get("altitude") or json_facts.get("altitude")
        roast_style = page_facts.get("roast_style") or json_facts.get("roast_style") or self._extract_roast_style(product_data)
        bag_size = page_facts.get("bag_size") or json_facts.get("bag_size") or self._extract_bag_size(product_data)
        tasting_notes = self._extract_tasting_notes(description, html_soup=html_soup, page_facts=page_facts)

        return CoffeeData(
            roaster=self.ROASTER_NAME,
            name=title,
            origin=normalize_country(origin),
            producer=producer,
            process=normalize_process(process),
            varietal=varietal,
            altitude=altitude,
            tasting_notes=tasting_notes,
            roast_style=roast_style,
            price_cents=self._extract_price(product_data),
            bag_size=bag_size,
            url=url,
            availability=bool(product_data.get("available", True)),
        )

    def _description_text(self, product_data: dict[str, Any]) -> str:
        """Flatten Shopify's HTML description into label-searchable text."""
        html = str(product_data.get("description") or "")
        return BeautifulSoup(html, "html.parser").get_text("\n", strip=True)

    def _extract_details(self, description: str) -> dict[str, str]:
        """Extract labeled metadata exposed in Shopify descriptions."""
        return extract_labeled_product_facts_from_text(
            description,
            label_aliases=self.PRODUCT_FACT_LABELS,
            stop_labels=self.PRODUCT_FACT_STOP_LABELS,
        )

    def _extract_html_product_facts(self, html_soup: BeautifulSoup) -> dict[str, str]:
        """Read product-page label/value sections before JSON fallbacks."""
        selected_facts: dict[str, str] = {}
        for selector in self.PRODUCT_FACT_SELECTORS:
            for block in html_soup.select(selector):
                block_facts = extract_labeled_product_facts_from_html(
                    block,
                    label_aliases=self.PRODUCT_FACT_LABELS,
                    stop_labels=self.PRODUCT_FACT_STOP_LABELS,
                )
                for key, value in block_facts.items():
                    selected_facts.setdefault(key, value)
        if selected_facts:
            return selected_facts

        return extract_labeled_product_facts_from_html(
            html_soup,
            label_aliases=self.PRODUCT_FACT_LABELS,
            stop_labels=self.PRODUCT_FACT_STOP_LABELS,
        )

    def _extract_details_from_title(self, title: str) -> dict[str, str | None]:
        """Try to extract origin and process from ``Origin - Name | Process`` titles."""
        details: dict[str, str | None] = {"origin": None, "process": None}
        if "|" in title:
            pipe_parts = [part.strip() for part in title.split("|")]
            details["origin"] = pipe_parts[0]
            if len(pipe_parts) >= 2:
                details["process"] = pipe_parts[-1]

        dash_pattern = r"\s*[-\u2012\u2013\u2014\u2212]\s*"
        if details["origin"]:
            dash_parts = re.split(dash_pattern, details["origin"])
            if dash_parts:
                details["origin"] = dash_parts[0]
        else:
            dash_parts = re.split(dash_pattern, title)
            if len(dash_parts) >= 2:
                details["origin"] = dash_parts[0]
                if len(dash_parts) >= 3:
                    details["process"] = dash_parts[-1]

        return details

    def _extract_tasting_notes(
        self,
        description: str,
        html_soup: BeautifulSoup | None = None,
        page_facts: dict[str, str] | None = None,
    ) -> list[str]:
        """Extract source-ordered notes from labeled facts before loose fallbacks."""
        if page_facts and page_facts.get("tasting_notes"):
            notes = normalize_tasting_notes(page_facts["tasting_notes"])
            if notes:
                return notes

        value = self._extract_details(description).get("tasting_notes")
        if value:
            notes = normalize_tasting_notes(value)
            if notes:
                return notes

        if html_soup:
            target = html_soup.select_one("p.product__text.inline-richtext.caption-with-letter-spacing")
            if target and target.get_text():
                notes = normalize_tasting_notes(target.get_text())
                if notes:
                    return notes

        lines = [line.strip() for line in description.splitlines() if line.strip()]
        if lines:
            first_line = lines[0]
            if len(first_line) < 100 and any(separator in first_line for separator in ("|", ",", ";", "+", "·", "•", "Â", "â")):
                return normalize_tasting_notes(first_line)

            note_lines: list[str] = []
            for line in lines:
                if line.lower() == "light" or re.search(r"\blight\b.*\bdark\b|[●○]", line, re.IGNORECASE):
                    break
                if len(line) > 60:
                    break
                note_lines.append(line)
                if len(note_lines) >= 7:
                    break

            combined_notes = " ".join(note_lines)
            if len(combined_notes) < 140 and any(separator in combined_notes for separator in ("·", "•", "Â", "â")):
                return normalize_tasting_notes(combined_notes)

        return []

    def _extract_roast_style(self, product_data: dict[str, Any]) -> str | None:
        """Use standard Shopify tags as a fallback roast-style classification."""
        tags = self._normalize_tags(product_data)
        styles = [style for style in ("filter", "espresso") if style in tags]
        return ", ".join(styles) if styles else None

    def _extract_price(self, product_data: dict[str, Any]) -> int | None:
        """Read Shopify's integer-cent product price when it is supplied."""
        price = product_data.get("price")
        return int(price) if isinstance(price, int) else None

    def _extract_bag_size(self, product_data: dict[str, Any]) -> str | None:
        """Find bag weight in Shopify variant fields or variant titles."""
        raw_variants: object = product_data.get("variants")
        if not isinstance(raw_variants, list):
            return None

        variants: list[dict[str, object]] = []
        for raw_variant in cast(list[object], raw_variants):
            if isinstance(raw_variant, dict):
                variants.append(cast(dict[str, object], raw_variant))

        if not variants:
            return None

        variant = variants[0]
        weight = variant.get("weight")
        unit = variant.get("weight_unit")
        if isinstance(weight, int | float) and isinstance(unit, str) and unit:
            return f"{int(weight)}{unit}"
        if isinstance(weight, int | float) and weight > 0:
            return f"{int(weight)}g"

        for variant in variants:
            for field in ("title", "public_title", "option1", "sku", "name"):
                raw_value = variant.get(field)
                value = raw_value if isinstance(raw_value, str) else ""
                match = re.search(r"\b\d+\s*(?:g|kg|oz|lb)\b", value, re.IGNORECASE)
                if match:
                    return match.group(0)
        return None


class PorteBleueScraper(ShopifyScraper):
    """Shopify configuration for Porte Bleue products."""

    BASE_URL = "https://portebleue.ca"
    COLLECTION_URL = f"{BASE_URL}/collections/coffee"
    SOURCE_NAME = "Porte Bleue"
    ROASTER_NAME = "Porte Bleue"


class ColorfullScraper(ShopifyScraper):
    """Shopify configuration for Colorfull, whose products lack coffee tags."""

    BASE_URL = "https://colorfullcoffee.com"
    COLLECTION_URL = f"{BASE_URL}/collections/all"
    SOURCE_NAME = "Colorfull"
    ROASTER_NAME = "Colorfull Coffee"
    INCLUDE_TAGS = ()
    EXCLUDE_HANDLE_KEYWORDS = ("gift", "subscription")


class AngryRoasterScraper(ShopifyScraper):
    """Shopify configuration for The Angry Roaster products."""

    BASE_URL = "https://theangryroaster.com"
    COLLECTION_URL = f"{BASE_URL}/collections/coffee"
    SOURCE_NAME = "The Angry Roaster"
    ROASTER_NAME = "The Angry Roaster"
    INCLUDE_TAGS = ("coffee",)


class TrafficScraper(ShopifyScraper):
    """Shopify configuration for Traffic products."""

    BASE_URL = "https://www.trafficcoffee.com"
    COLLECTION_URL = f"{BASE_URL}/collections/coffee"
    SOURCE_NAME = "Traffic"
    ROASTER_NAME = "Traffic Coffee"
    INCLUDE_TAGS = ()
    PRODUCT_FACT_STOP_LABELS = (*DEFAULT_PRODUCT_FACT_STOP_LABELS, "ABOUT")
    PRODUCT_FACT_SELECTORS = ("div.product-block-description",)


class DeMelloScraper(ShopifyScraper):
    """Shopify configuration for De Mello products."""

    BASE_URL = "https://hellodemello.com"
    COLLECTION_URL = f"{BASE_URL}/collections/all-coffee"
    SOURCE_NAME = "De Mello"
    ROASTER_NAME = "De Mello Coffee"
    INCLUDE_TAGS = ()
    EXCLUDE_HANDLE_KEYWORDS = (*ShopifyScraper.EXCLUDE_HANDLE_KEYWORDS, "starter-kit", "instant-coffee")
    PRODUCT_FACT_SELECTORS = ("div.metafield-rich_text_field",)
