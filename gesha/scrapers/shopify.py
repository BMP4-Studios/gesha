from __future__ import annotations

import re
from typing import Any, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

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
] + COMMON_TASTING_NOTE_LABELS


class ShopifyScraper(BaseScraper):
    COLLECTION_PATH = "/collections/coffee"
    PRODUCT_URL_PATTERN = re.compile(r"^/(?:collections/[^/]+/)?products/[^/?#]+$")
    INCLUDE_PRODUCT_TYPES: tuple[str, ...] = ()
    INCLUDE_TAGS: tuple[str, ...] = ("coffee",)
    EXCLUDE_HANDLE_KEYWORDS: tuple[str, ...] = ("subscription", "sub", "gift", "recurring")

    def extract_product_urls(self, html: str) -> List[str]:
        soup = BeautifulSoup(html, "html.parser")
        urls: list[str] = []
        for anchor in soup.select("a[href*='/products/']"):
            href = anchor.get("href", "").split("?", 1)[0].strip()
            if not self.PRODUCT_URL_PATTERN.match(href):
                continue
            urls.append(self._canonical_product_url(urljoin(self.BASE_URL, href)))
        return sorted(dict.fromkeys(urls))

    def scrape_product(self, url: str) -> Optional[CoffeeData]:
        """Shopify-specific product scraping using the .js AJAX endpoint."""
        response = self.session.get(f"{url}.js", timeout=15)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        product_data = response.json()

        if not self._is_coffee_product(product_data):
            return None
        
        # If the JSON description is missing key details, fetch HTML as a fallback
        html_soup = None
        # We check for tasting notes as a proxy for whether the JSON description is sufficient
        if not self._extract_tasting_notes(self._description_text(product_data)): 
            res_html = self.session.get(url, timeout=15)
            if res_html.status_code == 200:
                html_soup = BeautifulSoup(res_html.text, "html.parser")

        # Convert fallback soup to clean text if we have it
        # This is used for general labeled value extraction if specific selectors fail
        # and also passed to _extract_tasting_notes
        html_text = None
        if html_soup:
            html_text = html_soup.get_text("\n", strip=True)

        return self._coffee_from_product(product_data, url, html_text=html_text, html_soup=html_soup)

    def parse_product(self, html: str, url: str) -> CoffeeData:
        raise NotImplementedError("ShopifyScraper parses product JSON instead of product HTML.")

    def _canonical_product_url(self, url: str) -> str:
        parsed = urlparse(url)
        handle = parsed.path.rstrip("/").rsplit("/", 1)[-1]
        return urljoin(self.BASE_URL, f"/products/{handle}")

    def _is_coffee_product(self, product_data: dict[str, Any]) -> bool:
        handle = str(product_data.get("handle") or "").lower()
        tags = {str(tag).strip().lower() for tag in product_data.get("tags") or []}

        # Exclude handles or tags containing subscription keywords
        if any(kw in handle for kw in self.EXCLUDE_HANDLE_KEYWORDS) or \
           any(kw in tags for kw in self.EXCLUDE_HANDLE_KEYWORDS):
            return False
        product_type = str(product_data.get("type") or "").strip().lower()

        if self.INCLUDE_PRODUCT_TYPES and product_type in {value.lower() for value in self.INCLUDE_PRODUCT_TYPES}:
            return True
        if self.INCLUDE_TAGS and tags.intersection({value.lower() for value in self.INCLUDE_TAGS}):
            return True
        return not self.INCLUDE_PRODUCT_TYPES and not self.INCLUDE_TAGS

    def _coffee_from_product(
        self, 
        product_data: dict[str, Any], 
        url: str, 
        html_text: str = None, 
        html_soup: BeautifulSoup = None
    ) -> CoffeeData:
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

    def _extract_details_from_title(self, title: str) -> dict[str, Optional[str]]:
        """Try to extract origin and process from common title patterns like 'Country - Name | Process'."""
        details = {"origin": None, "process": None}
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
        html_soup: BeautifulSoup = None, 
        html_text: str = None,
        html_block_notes_raw: str = None
    ) -> list[str]:
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
                r"in the cup (?:you can find|you'll find|is|are)?\s*(.+?)(?:\.|$)",
                r"(?:notes of|profile of)\s+(.+?)(?:\.|$)",
            ):
                match = re.search(pattern, description, re.IGNORECASE | re.DOTALL)
                if match:
                    value = match.group(1)
                    break
        if not value:
            # Fallback to the very first line of the description if no label is found
            lines = [l.strip() for l in description.splitlines() if l.strip()]
            # Try to find a line that actually looks like a note list (using special separators)
            for line in lines:
                if any(sep in line for sep in ("•", "·", "|")):
                    value = line
                    break
            if lines:
                value = value or lines[0]
        if not value:
            return []
        # Support standard separators plus bullets, middle dots, and period-space
        parts = re.split(r"[,;/]|&|\s+-\s+|[•·|]|\.\s+", value)
        return normalize_tasting_notes(clean_tasting_note_candidates(parts))

    def _extract_roast_style(self, product_data: dict[str, Any]) -> Optional[str]:
        tags = {str(tag).strip().lower() for tag in product_data.get("tags") or []}
        styles = [style for style in ("filter", "espresso") if style in tags]
        return ", ".join(styles) if styles else None

    def _extract_price(self, product_data: dict[str, Any]) -> Optional[int]:
        price = product_data.get("price")
        return int(price) if isinstance(price, int) else None

    def _extract_bag_size(self, product_data: dict[str, Any]) -> Optional[str]:
        variants = product_data.get("variants") or []
        if not variants:
            return None
        # Check first variant for weight info
        variant = variants[0]
        weight = variant.get("weight")
        unit = variant.get("weight_unit")
        if weight and unit:
            return f"{int(weight)}{unit}"

        # Fallback to variant title regex
        for v in variants:
            title = str(v.get("title") or "")
            match = re.search(r"\b\d+\s*(?:g|kg|oz|lb)\b", title, re.IGNORECASE)
            if match:
                return match.group(0)
        return None

    def _extract_details_from_html_block(self, html_soup: BeautifulSoup) -> dict[str, Optional[str]]:
        """
        Extracts details from a specific HTML block like the one found in Porte Bleue's accordion.
        This targets <p><strong>Label: </strong>Value<br/>...</p> patterns.
        """
        details = {}
        accordion_content_p = html_soup.select_one("div.accordion__content.rte p")
        if accordion_content_p:
            # Get the raw HTML content of the <p> tag
            raw_html_content = str(accordion_content_p)
            # Replace <br/> with newlines to make it easier for extract_labeled_value
            text_block = raw_html_content.replace("<br/>", "\n")
            # Use BeautifulSoup to get clean text from the modified block
            clean_text_block = BeautifulSoup(text_block, "html.parser").get_text("\n", strip=True)

            details["origin"] = extract_labeled_value(clean_text_block, ["Country"], SHOPIFY_DETAIL_LABELS)
            details["producer"] = extract_labeled_value(clean_text_block, ["Producer"], SHOPIFY_DETAIL_LABELS)
            details["process"] = extract_labeled_value(clean_text_block, ["Process"], SHOPIFY_DETAIL_LABELS)
            details["varietal"] = extract_labeled_value(clean_text_block, ["Variety"], SHOPIFY_DETAIL_LABELS)
            details["altitude"] = extract_labeled_value(clean_text_block, ["Altitude"], SHOPIFY_DETAIL_LABELS)
            details["tasting_notes_raw"] = extract_labeled_value(clean_text_block, COMMON_TASTING_NOTE_LABELS, SHOPIFY_DETAIL_LABELS)
        return details


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


class RogueWaveScraper(ShopifyScraper):
    BASE_URL = "https://www.roguewavecoffee.ca"
    COLLECTION_URL = f"{BASE_URL}/collections/coffee"
    SOURCE_NAME = "Rogue Wave"
    ROASTER_NAME = "Rogue Wave Coffee"
    INCLUDE_TAGS = ("coffee",)


class HouseOfFunkScraper(ShopifyScraper):
    BASE_URL = "https://www.houseoffunkbrewing.com"
    COLLECTION_URL = f"{BASE_URL}/collections/coffee"
    SOURCE_NAME = "House of Funk"
    ROASTER_NAME = "House of Funk"
    INCLUDE_TAGS = ("coffee",)
