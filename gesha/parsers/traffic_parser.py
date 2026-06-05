from __future__ import annotations

import re
from typing import List, Optional

from bs4 import BeautifulSoup

from gesha.models.coffee import CoffeeData
from gesha.normalization.normalize import (
    normalize_country,
    normalize_process,
    normalize_tasting_notes,
)
from gesha.parsers.common import (
    clean_tasting_note_candidates,
    extract_labeled_value,
    extract_matching_urls,
    extract_text,
    parse_price,
)

PRODUCT_URL_PATTERN = re.compile(r"^/collections/coffee/products/[^/?#]+$")
DETAIL_LABELS = [
    "Farmer",
    "Origin",
    "Process",
    "Varietal",
    "Altitude",
    "Roast level",
    "Size",
    "In the cup",
    "About",
    "ABOUT",
]


def parse_traffic_collection(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls = extract_matching_urls(
        soup,
        selector="a[href*='/products/']",
        attribute="href",
        base_url=base_url,
        pattern=PRODUCT_URL_PATTERN,
    )

    return sorted(dict.fromkeys(urls))


def _parse_traffic_details(text: str) -> dict[str, Optional[str]]:
    details = {
        "origin": None,
        "producer": None,
        "process": None,
        "varietal": None,
        "altitude": None,
        "roast_style": None,
        "bag_size": None,
    }

    def value_for(key: str) -> Optional[str]:
        return extract_labeled_value(text, [key], DETAIL_LABELS)

    details["origin"] = value_for("Origin")
    details["producer"] = value_for("Farmer")
    details["process"] = value_for("Process")
    details["varietal"] = value_for("Varietal")
    details["altitude"] = value_for("Altitude")
    details["roast_style"] = value_for("Roast level")
    details["bag_size"] = value_for("Size")
    return details


def _extract_tasting_notes(text: str) -> List[str]:
    value = extract_labeled_value(text, ["In the cup"], DETAIL_LABELS)
    if not value:
        return []
    return normalize_tasting_notes(clean_tasting_note_candidates(re.split(r"[,;/]|\s+-\s+", value)))


def parse_traffic_product(html: str, url: str) -> CoffeeData:
    soup = BeautifulSoup(html, "html.parser")
    title = extract_text(soup.select_one("h1")) or "Unknown coffee"

    price_text = extract_text(soup.select_one("span[class*='price']"))
    price_cents = parse_price(price_text)

    desc_div = soup.select_one("div.product-block-description")
    description = extract_text(desc_div) if desc_div else ""

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
        bag_size=details.get("bag_size"),
        url=url,
    )
