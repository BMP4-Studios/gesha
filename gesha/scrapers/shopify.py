"""Shopify-oriented scraping and adapters for several supported roasters.

The generic ``ShopifyScraper`` favors Shopify's product JSON endpoint and
supplements it with HTML when theme-specific detail blocks contain better
metadata. Simple HTML-only adapters at the bottom delegate to parser modules.
"""

from __future__ import annotations

import re
from typing import Any, cast
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from gesha.models.coffee import CoffeeData
from gesha.normalization.normalize import normalize_country, normalize_process, normalize_tasting_notes, remove_emojis
from gesha.parsers.common import COMMON_TASTING_NOTE_LABELS, clean_tasting_note_candidates, extract_labeled_value
from gesha.scrapers.base import BaseScraper


SHOPIFY_DETAIL_LABELS = [
    "Country",
    "Origin",
    "Origins",
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
    "Amount",
    "Size",
    "Specs",
    "Roast Level",
    "Roast Style",
    "Roast",
] + COMMON_TASTING_NOTE_LABELS


class ShopifyScraper(BaseScraper):
    """Extract coffee products from stores exposing Shopify product JSON."""

    COLLECTION_PATH = "/collections/coffee"
    PRODUCT_URL_PATTERN = re.compile(r"^/(?:collections/[^/]+/)?products/[^/?#]+$")
    INCLUDE_TAGS: tuple[str, ...] = ("coffee",)
    EXCLUDE_HANDLE_KEYWORDS: tuple[str, ...] = ("subscription", "sub", "gift", "recurring")

    def extract_product_urls(self, html: str) -> list[str]:
        """Convert collection product links into canonical Shopify product URLs."""
        soup = BeautifulSoup(html, "html.parser")
        urls: list[str] = []
        for anchor in soup.select("a[href*='/products/']"):
            raw_href = anchor.get("href")
            if not isinstance(raw_href, str):
                continue
            href = raw_href.split("?", 1)[0].strip()
            if not self.PRODUCT_URL_PATTERN.match(href):
                continue
            urls.append(self._canonical_product_url(urljoin(self.BASE_URL, href)))
        return sorted(dict.fromkeys(urls))

    def scrape_product(self, url: str) -> CoffeeData | None:
        """Fetch Shopify JSON and optional HTML fallback for one product."""
        # Add Referer header to make the .js request look more legitimate
        session = cast(Any, self.session)
        headers = session.headers.copy()
        headers["Referer"] = url # The HTML product page is the referer for the .js endpoint
        response = session.get(f"{url}.js", headers=headers, timeout=15)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        product_data = cast(dict[str, Any], response.json())

        if not self._is_coffee_product(product_data):
            return None
        
        # If the JSON description is missing key details, fetch HTML as a fallback
        html_soup: BeautifulSoup | None = None
        description_text = self._description_text(product_data)
        
        # Heuristic: fetch HTML if JSON lacks structured labels for origin or notes.
        # Narrative descriptions (like Porte Bleue's) often don't match labeled extraction.
        has_structured_origin = bool(self._extract_details(description_text).get("origin"))
        has_structured_notes = bool(self._extract_tasting_notes(description_text))

        if not (has_structured_origin and has_structured_notes):
            res_html = self.session.get(url, timeout=15)
            if res_html.status_code == 200:
                html_soup = BeautifulSoup(res_html.text, "html.parser")

        # Convert fallback soup to clean text if we have it
        # This is used for general labeled value extraction if specific selectors fail
        # and also passed to _extract_tasting_notes
        html_text: str | None = None
        if html_soup:
            html_text = html_soup.get_text("\n", strip=True)

        return self._coffee_from_product(product_data, url, html_text=html_text, html_soup=html_soup)

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
        raw_tags = product_data.get("tags") or [] # type: ignore
        if isinstance(raw_tags, str):
            raw_tags = [tag.strip() for tag in raw_tags.split(",") if tag.strip()]
        return {str(tag).strip().lower() for tag in raw_tags if str(tag).strip()}

    def _is_coffee_product(self, product_data: dict[str, Any]) -> bool:
        """Reject subscriptions and accept products satisfying source tag rules."""
        handle = str(product_data.get("handle") or "").lower()
        tags = self._normalize_tags(product_data)

        # Exclude handles or tags containing subscription keywords
        if any(kw in handle for kw in self.EXCLUDE_HANDLE_KEYWORDS) or \
           any(kw in tags for kw in self.EXCLUDE_HANDLE_KEYWORDS):
            return False

        if self.INCLUDE_TAGS and tags.intersection({value.lower() for value in self.INCLUDE_TAGS}):
            return True

        return not self.INCLUDE_TAGS

    def _coffee_from_product(
        self, 
        product_data: dict[str, Any], 
        url: str, 
        html_text: str | None = None, 
        html_soup: BeautifulSoup | None = None
    ) -> CoffeeData:
        """Merge Shopify and theme HTML fields into the shared catalog model."""
        description = self._description_text(product_data)
        details = self._extract_details(description)
        title = remove_emojis(str(product_data.get("title") or "Unknown coffee"))

        # Fallback to title parsing if description labels are missing
        title_details = self._extract_details_from_title(title)

        # Extract details from specific HTML block (like accordions) if available
        html_block_details = self._extract_details_from_html_block(html_soup) if html_soup else {}

        # Prioritize details from HTML block, then JSON description, then title
        origin = html_block_details.get("origin") or details.get("origin") or title_details.get("origin") or title
        producer = html_block_details.get("producer") or details.get("producer")
        process = html_block_details.get("process") or details.get("process") or title_details.get("process") or title
        varietal = html_block_details.get("varietal") or details.get("varietal")
        altitude = html_block_details.get("altitude") or details.get("altitude")
        roast_style = html_block_details.get("roast_style") or details.get("roast_style") or self._extract_roast_style(product_data)

        # Tasting notes can come from multiple places, prioritize specific HTML block if found
        tasting_notes = self._extract_tasting_notes(
            description, 
            html_soup=html_soup, 
            html_text=html_text,
            html_block_notes_raw=html_block_details.get("tasting_notes_raw")
        )
        
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
            bag_size=details.get("bag_size") or self._extract_bag_size(product_data),
            url=url,
            availability=bool(product_data.get("available", True)),
        )

    def _description_text(self, product_data: dict[str, Any]) -> str:
        """Flatten Shopify's HTML description into label-searchable text."""
        html = str(product_data.get("description") or "")
        return BeautifulSoup(html, "html.parser").get_text("\n", strip=True)

    def _extract_details(self, description: str) -> dict[str, str | None]:
        """Extract generic labeled metadata exposed in Shopify descriptions."""
        return {
            "origin": extract_labeled_value(description, ["Origin", "Country", "Region", "Place"], SHOPIFY_DETAIL_LABELS),
            "producer": extract_labeled_value(description, ["Coffee Producers", "Producer", "Producers", "Farm"], SHOPIFY_DETAIL_LABELS),
            "process": extract_labeled_value(description, ["Process", "Method"], SHOPIFY_DETAIL_LABELS),
            "varietal": extract_labeled_value(description, ["Variety", "Varieties", "Cultivar"], SHOPIFY_DETAIL_LABELS),
            "altitude": extract_labeled_value(description, ["Altitude", "Elevation"], SHOPIFY_DETAIL_LABELS),
            "bag_size": extract_labeled_value(description, ["Amount", "Size", "Specs"], SHOPIFY_DETAIL_LABELS),
            "roast_style": extract_labeled_value(description, ["Roast Level", "Roast Style", "Roast"], SHOPIFY_DETAIL_LABELS),
        }

    def _extract_details_from_title(self, title: str) -> dict[str, str | None]:
        """Try to extract origin and process from common title patterns like 'Country - Name | Process'."""
        details: dict[str, str | None] = {"origin": None, "process": None}
        # Split by pipe first (highest confidence for process)
        if "|" in title:
            pipe_parts = [p.strip() for p in title.split("|")]
            details["origin"] = pipe_parts[0]
            if len(pipe_parts) >= 2:
                # If there are 3+ parts (Origin | Name | Process), use the last
                details["process"] = pipe_parts[-1]
        # Refine origin if it was set or try dash split
        if details["origin"]:
            dash_parts = re.split(r"\s*[−–—-]\s*", details["origin"])
            if dash_parts:
                details["origin"] = dash_parts[0]
        else:
            # No pipe, fallback to dash split
            dash_parts = re.split(r"\s*[−–—-]\s*", title)
            if len(dash_parts) >= 2:
                details["origin"] = dash_parts[0]
                if len(dash_parts) >= 3:
                    details["process"] = dash_parts[-1]

        return details

    def _extract_tasting_notes(
        self, 
        description: str, 
        html_soup: BeautifulSoup | None = None, 
        html_text: str | None = None,
        html_block_notes_raw: str | None = None
    ) -> list[str]:
        """Extract notes from structured blocks, theme markup, or description prose."""
        # Prioritize notes from the specific HTML block if provided
        if html_block_notes_raw:
            notes = normalize_tasting_notes(clean_tasting_note_candidates(re.split(r"[;,\n•·|]|\.\s+", html_block_notes_raw)))
            if notes:
                return notes

        # 1. Try Porte Bleue / common theme "subtitle" notes pattern in the HTML soup
        if html_soup:
            # This targets the specific paragraph under the title found on Porte Bleue and others
            target = html_soup.select_one("p.product__text.inline-richtext.caption-with-letter-spacing")
            if target and target.get_text():
                notes = normalize_tasting_notes(clean_tasting_note_candidates(re.split(r"[•·|]", target.get_text())))
                if notes:
                    return notes

        # 2. Try labeled extraction on description (JSON text) or fallback text (HTML cleaned to text)
        source = html_text if (html_text and not description.strip()) else description
        value = extract_labeled_value(source, COMMON_TASTING_NOTE_LABELS, SHOPIFY_DETAIL_LABELS)
        
        if not value:
            for pattern in (
                r"(?:in the cup|we taste|tastes like|notes of|profile of|flavour profile is)\s*(?:you can find|you'll find|is|are)?\s*(.+?)(?:\.|$)",
            ):
                match = re.search(pattern, description, re.IGNORECASE | re.DOTALL)
                if match:
                    value = match.group(1)
                    break
        if not value:
            # Fallback to the first line only if it looks like a list (short and has separators)
            lines = [l.strip() for l in description.splitlines() if l.strip()]
            if lines:
                first_line = lines[0]
                if len(first_line) < 100 and any(sep in first_line for sep in ("•", "·", "|", ",", ";")):
                    value = first_line
        if not value:
            return []
        # Support standard separators plus bullets, middle dots, and period-space
        parts = re.split(r"[,;/]|&|\s+and\s+|\s+-\s+|[•·|]|\.\s+", value, flags=re.IGNORECASE)
        return normalize_tasting_notes(clean_tasting_note_candidates(parts))

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

        # Check first variant for weight info
        variant = variants[0]
        weight = variant.get("weight")
        unit = variant.get("weight_unit")
        
        if isinstance(weight, int | float) and isinstance(unit, str) and unit:
            return f"{int(weight)}{unit}"

        # Fallback to variant title regex
        for variant in variants:
            raw_title = variant.get("title")
            title = raw_title if isinstance(raw_title, str) else ""
            match = re.search(r"\b\d+\s*(?:g|kg|oz|lb)\b", title, re.IGNORECASE)
            if match:
                return match.group(0)
        return None

    def _extract_details_from_html_block(self, html_soup: BeautifulSoup) -> dict[str, str | None]:
        """
        Extract label/value fields from accordion markup used by some themes.

        Porte Bleue, for example, exposes more complete product metadata in
        ``<p><strong>Label:</strong> Value<br/>...</p>`` HTML than in JSON.
        """
        details = {}
        accordion_content_p: Tag | None = html_soup.select_one("div.accordion__content.rte p")
        if accordion_content_p:
            # Get the raw HTML content of the <p> tag
            raw_html_content = str(accordion_content_p)
            # Replace <br/> with newlines to make it easier for extract_labeled_value
            text_block = raw_html_content.replace("<br/>", "\n")
            # Use BeautifulSoup to get clean text from the modified block
            clean_text_block = BeautifulSoup(text_block, "html.parser").get_text("\n", strip=True)

            details = self._extract_details(clean_text_block)
            details["tasting_notes_raw"] = extract_labeled_value(clean_text_block, COMMON_TASTING_NOTE_LABELS, SHOPIFY_DETAIL_LABELS)
        return details


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


class RogueWaveScraper(ShopifyScraper):
    """Shopify configuration retained for potential explicit registry use."""

    BASE_URL = "https://www.roguewavecoffee.ca"
    COLLECTION_URL = f"{BASE_URL}/collections/coffee"
    SOURCE_NAME = "Rogue Wave"
    ROASTER_NAME = "Rogue Wave Coffee"
    INCLUDE_TAGS = ("coffee",)


class HouseOfFunkScraper(ShopifyScraper):
    """Shopify configuration retained for potential explicit registry use."""

    BASE_URL = "https://www.houseoffunkbrewing.com"
    COLLECTION_URL = f"{BASE_URL}/collections/coffee"
    SOURCE_NAME = "House of Funk"
    ROASTER_NAME = "House of Funk"
    INCLUDE_TAGS = ("coffee",)

# These HTML-backed adapters share transport behavior with BaseScraper, but
# their page structures are sufficiently distinct to live in parser modules.
from gesha.parsers.traffic_parser import parse_traffic_collection, parse_traffic_product
class TrafficScraper(BaseScraper):
    """HTML scraper adapter that delegates Traffic markup parsing."""

    BASE_URL = "https://www.trafficcoffee.com"
    COLLECTION_URL = f"{BASE_URL}/collections/coffee"
    SOURCE_NAME = "Traffic"
    ROASTER_NAME = "Traffic Coffee"
    INCLUDE_TAGS = ("coffee",)

    def extract_product_urls(self, html: str) -> list[str]:
        """Discover Traffic product pages in collection HTML."""
        return parse_traffic_collection(html, base_url=self.BASE_URL)

    def parse_product(self, html: str, url: str) -> CoffeeData:
        """Delegate Traffic page normalization to its source-specific parser."""
        return parse_traffic_product(html, url)

from gesha.parsers.demello_parser import parse_demello_collection, parse_demello_product
class DeMelloScraper(BaseScraper):
    """HTML scraper adapter that delegates De Mello markup parsing."""

    BASE_URL = "https://hellodemello.com"
    COLLECTION_URL = f"{BASE_URL}/collections/all-coffee"
    SOURCE_NAME = "De Mello"
    ROASTER_NAME = "De Mello Coffee"
    INCLUDE_TAGS = ("coffee",)

    def extract_product_urls(self, html: str) -> list[str]:
        """Discover De Mello product pages in collection HTML."""
        return parse_demello_collection(html, base_url=self.BASE_URL)

    def parse_product(self, html: str, url: str) -> CoffeeData:
        """Delegate De Mello page normalization to its source-specific parser."""
        return parse_demello_product(html, url)
