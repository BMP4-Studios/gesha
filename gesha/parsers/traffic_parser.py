"""Parse Traffic Coffee theme pages for the Traffic scraper adapter.

Traffic uses an HTML description block with labeled fields, so this module
isolates its selectors and extraction choices from generic scraping transport.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from gesha.models.coffee import CoffeeData
from gesha.normalization.normalize import normalize_country, normalize_process, normalize_tasting_notes
from gesha.parsers.common import COMMON_TASTING_NOTE_LABELS, clean_tasting_note_candidates, extract_labeled_value, extract_matching_urls, extract_shopify_bag_size, extract_text, parse_price

PRODUCT_URL_PATTERN = re.compile(r"^/collections/coffee/products/[^/?#]+$")
DETAIL_LABELS = [
    "Farmer",
    "Origin",
    "Process",
    "Varietal",
    "Altitude",
    "Roast level",
    "Size",
    "About",
    "ABOUT",
] + COMMON_TASTING_NOTE_LABELS


def parse_traffic_collection(html: str, base_url: str) -> list[str]:
    """Extract unique coffee product URLs from Traffic's collection markup."""
    soup = BeautifulSoup(html, "html.parser")
    urls = extract_matching_urls(
        soup,
        selector="a[href*='/products/']",
        attribute="href",
        base_url=base_url,
        pattern=PRODUCT_URL_PATTERN,
    )

    return sorted(dict.fromkeys(urls))


def _parse_traffic_details(text: str) -> dict[str, str | None]:
    """Extract Traffic's labeled description values into catalog fields."""
    details: dict[str, str | None] = {
        "origin": None,
        "producer": None,
        "process": None,
        "varietal": None,
        "altitude": None,
        "roast_style": None,
        "bag_size": None,
    }

    def value_for(key: str) -> str | None:
        """Read one Traffic detail label using the module's stop labels."""
        return extract_labeled_value(text, [key], DETAIL_LABELS)

    details["origin"] = value_for("Origin")
    details["producer"] = value_for("Farmer")
    details["process"] = value_for("Process")
    details["varietal"] = value_for("Varietal")
    details["altitude"] = value_for("Altitude")
    details["roast_style"] = value_for("Roast level")
    details["bag_size"] = value_for("Size")
    return details


def _extract_tasting_notes(text: str) -> list[str]:
    """Clean tasting notes embedded among Traffic's product detail labels."""
    value = extract_labeled_value(text, COMMON_TASTING_NOTE_LABELS, DETAIL_LABELS)
    if not value:
        return []
    return normalize_tasting_notes(clean_tasting_note_candidates(re.split(r"[,;/]|\s+-\s+", value)))


def parse_traffic_product(html: str, url: str) -> CoffeeData:
    """Build one validated catalog item from a Traffic product HTML page."""
    soup = BeautifulSoup(html, "html.parser")
    title = extract_text(soup.select_one("h1")) or "Unknown coffee"

    price_text = extract_text(soup.select_one("span[class*='price']"))
    price_cents = parse_price(price_text)

    # Traffic keeps most useful metadata in a single product description
    # element, allowing shared label extraction for each field.
    desc_div = soup.select_one("div.product-block-description")
    description = extract_text(desc_div) if desc_div else ""
    if description is None:
        description = ""

    details = _parse_traffic_details(description)
    tasting_notes = _extract_tasting_notes(description)

    return CoffeeData(
        roaster="Traffic Coffee",
        name=title,
        origin=normalize_country(details.get("origin")) or normalize_country(title),
        producer=details.get("producer"),
        process=normalize_process(details.get("process")) or normalize_process(title),
        varietal=details.get("varietal"),
        altitude=details.get("altitude"),
        tasting_notes=tasting_notes,
        roast_style=details.get("roast_style"),
        price_cents=price_cents,
        bag_size=details.get("bag_size") or extract_shopify_bag_size(soup, title, url),
        url=url,
    )
