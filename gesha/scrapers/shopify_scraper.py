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
from gesha.normalization import normalize_search_text, normalize_tasting_notes
from gesha.parsers.common import (
    DEFAULT_PRODUCT_FACT_LABELS,
    DEFAULT_PRODUCT_FACT_STOP_LABELS,
    extract_labeled_product_facts_from_html,
    extract_labeled_product_facts_from_text,
)
from gesha.scrapers.base_scraper import BaseScraper


def _first_non_blank(*values: str | None) -> str | None:
    """Return the first source value that carries actual content."""
    for value in values:
        if value:
            cleaned = value.strip()
            if cleaned:
                return cleaned
    return None


class ShopifyScraper(BaseScraper):
    """Extract coffee products from stores exposing Shopify product JSON."""

    PRODUCT_URL_PATTERN = re.compile(r"^/(?:collections/[^/]+/)?products/[^/?#]+$")
    PRODUCT_LINK_ATTRIBUTES: tuple[str, ...] = ("href", "data-url")
    INCLUDE_TAGS: tuple[str, ...] = ("coffee",)
    EXCLUDE_HANDLE_KEYWORDS: tuple[str, ...] = ("subscription", "sub", "gift", "recurring")
    PRODUCT_FACT_LABELS = DEFAULT_PRODUCT_FACT_LABELS
    PRODUCT_FACT_STOP_LABELS = DEFAULT_PRODUCT_FACT_STOP_LABELS
    PRODUCT_FACT_SELECTORS: tuple[str, ...] = ()
    # some roasters (Rogue?) use dashes to add the origin to the title. Enable this by setting the flag to True
    EXTRACT_DASH_TITLE_FACTS = False
    NOTE_HINT_SEPARATORS = ("|", ",", ";", "+", "·", "•", "Â", "â")
    BULLET_NOTE_SEPARATORS = ("·", "•", "Â", "â")
    ROAST_SCALE_PATTERN = re.compile(r"\blight\b.*\bdark\b|[●○]", re.IGNORECASE)

    def extract_product_urls(self, html: str) -> list[str]:
        """Convert collection product links into canonical Shopify product URLs."""
        soup = BeautifulSoup(html, "html.parser")
        urls: list[str] = []

        # Shopify themes expose product targets in anchors and data attributes.
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

                # Canonicalize collection links before de-duping at the end.
                urls.append(self._canonical_product_url(urljoin(self.BASE_URL, href)))
        return sorted(dict.fromkeys(urls))

    def scrape_product(self, url: str) -> CoffeeData | None:
        """Fetch Shopify HTML first, then JSON support data for one product."""
        # Product-page HTML usually carries the richest label/value metadata.
        html_soup: BeautifulSoup | None = None
        html_facts: dict[str, str] = {}
        res_html = self.session.get(url, timeout=15)
        if res_html.status_code == 200:
            html_soup = BeautifulSoup(res_html.text, "html.parser")
            html_facts = self._extract_html_product_facts(html_soup)

        # Shopify JSON is still the reliable source for title, variants, price,
        # availability, tags, and description fallbacks.
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

        # Merge the page facts and Shopify payload into the normalized DTO.
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

        # Excluded handles/tags catch subscription, gift, and kit-like products.
        if self._is_excluded_handle(handle) or any(keyword in tags for keyword in self.EXCLUDE_HANDLE_KEYWORDS):
            return False

        # Some roasters tag coffee reliably; others configure INCLUDE_TAGS empty.
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
        # Extract every source of structured facts before choosing precedence.
        description = self._description_text(product_data)
        json_facts = self._extract_details(description)
        page_facts = html_facts or (self._extract_html_product_facts(html_soup) if html_soup else {})
        title = normalize_search_text(str(product_data.get("title") or "Unknown coffee")) or "unknown coffee"
        title_facts = self._extract_details_from_title(title)

        # Prefer explicit page labels, then Shopify description labels, then
        # title heuristics only for fields titles can express safely.
        origin = _first_non_blank(page_facts.get("origin"), json_facts.get("origin"), title_facts.get("origin"))
        producer = _first_non_blank(page_facts.get("producer"), json_facts.get("producer"))
        process = _first_non_blank(page_facts.get("process"), json_facts.get("process"), title_facts.get("process"))
        varietal = _first_non_blank(page_facts.get("varietal"), json_facts.get("varietal"))
        altitude = _first_non_blank(page_facts.get("altitude"), json_facts.get("altitude"))
        roast_style = _first_non_blank(
            page_facts.get("roast_style"),
            json_facts.get("roast_style"),
            self._extract_roast_style(product_data),
        )
        bag_size = _first_non_blank(
            page_facts.get("bag_size"),
            json_facts.get("bag_size"),
            self._extract_bag_size(product_data),
        )
        tasting_notes = self._extract_tasting_notes(
            description,
            html_soup=html_soup,
            page_facts=page_facts,
            json_facts=json_facts,
        )

        # Normalize at the boundary so database and display layers stay simple.
        return CoffeeData(
            roaster = self.ROASTER_NAME,
            name = title,
            origin = normalize_search_text(origin),
            producer = producer,
            process = normalize_search_text(process),
            varietal = varietal,
            altitude = altitude,
            tasting_notes = tasting_notes,
            roast_style = roast_style,
            price_cents = self._extract_price(product_data),
            bag_size = bag_size,
            url = url,
            availability = bool(product_data.get("available", True)),
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

        # Source configs can point directly at known metadata blocks.
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

        # If no selector is configured or populated, scan the whole product page.
        return extract_labeled_product_facts_from_html(
            html_soup,
            label_aliases=self.PRODUCT_FACT_LABELS,
            stop_labels=self.PRODUCT_FACT_STOP_LABELS,
        )

    def _extract_details_from_title(self, title: str) -> dict[str, str | None]:
        """Try to extract origin and process from ``Origin - Name | Process`` titles."""
        details: dict[str, str | None] = {"origin": None, "process": None}

        # Pipe-separated titles usually put process on the far right.
        if "|" in title:
            pipe_parts = [part.strip() for part in title.split("|")]
            details["origin"] = pipe_parts[0]
            if len(pipe_parts) >= 2:
                details["process"] = pipe_parts[-1]

        # Pipe-separated origins may still include a dash-separated coffee name.
        dash_pattern = r"\s*[-\u2012\u2013\u2014\u2212]\s*"
        if details["origin"]:
            dash_parts = re.split(dash_pattern, details["origin"])
            if dash_parts:
                details["origin"] = dash_parts[0]

        elif self.EXTRACT_DASH_TITLE_FACTS:
            # Dash-only titles are ambiguous, so sources opt in after fixtures
            # prove they consistently use ``Origin - Name - Process``.
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
        json_facts: dict[str, str] | None = None,
    ) -> list[str]:
        """Extract source-ordered notes from labeled facts before loose fallbacks."""
        # Labeled product-page facts are the highest-confidence notes source.
        if page_facts and page_facts.get("tasting_notes"):
            notes = normalize_tasting_notes(page_facts["tasting_notes"])
            if notes:
                return notes

        # Shopify descriptions often repeat the same labels without page markup.
        facts = json_facts if json_facts is not None else self._extract_details(description)
        value = facts.get("tasting_notes")
        if value:
            notes = normalize_tasting_notes(value)
            if notes:
                return notes

        # Some themes render notes as a short standalone caption.
        if html_soup:
            target = html_soup.select_one("p.product__text.inline-richtext.caption-with-letter-spacing")
            if target and target.get_text():
                notes = normalize_tasting_notes(target.get_text())
                if notes:
                    return notes

        # Last chance: only accept very short note-like leading text.
        lines = [line.strip() for line in description.splitlines() if line.strip()]
        if lines:
            first_line = lines[0]
            if len(first_line) < 100 and any(separator in first_line for separator in self.NOTE_HINT_SEPARATORS):
                return normalize_tasting_notes(first_line)

            note_lines: list[str] = []
            for line in lines:
                if line.lower() == "light" or self.ROAST_SCALE_PATTERN.search(line):
                    break
                if len(line) > 60:
                    break
                note_lines.append(line)
                if len(note_lines) >= 7:
                    break

            combined_notes = " ".join(note_lines)
            if len(combined_notes) < 140 and any(
                separator in combined_notes for separator in self.BULLET_NOTE_SEPARATORS
            ):
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
        # Shopify stores variant metadata as an untyped list in product JSON.
        raw_variants: object = product_data.get("variants")
        if not isinstance(raw_variants, list):
            return None

        variants: list[dict[str, object]] = []
        for raw_variant in cast(list[object], raw_variants):
            if isinstance(raw_variant, dict):
                variants.append(cast(dict[str, object], raw_variant))

        if not variants:
            return None

        # Prefer first-variant weight fields when Shopify supplies them.
        variant = variants[0]
        weight = variant.get("weight")
        unit = variant.get("weight_unit")
        if isinstance(weight, int | float) and isinstance(unit, str) and unit:
            return f"{int(weight)}{unit}"
        if isinstance(weight, int | float) and weight > 0:
            return f"{int(weight)}g"

        # Some roasters leave weight at zero but put "227g" in variant text.
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
