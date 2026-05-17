from __future__ import annotations

import re
from typing import List, Optional

from bs4 import BeautifulSoup

from gesha.models.coffee import CoffeeData
from gesha.normalization.normalize import normalize_country, normalize_process, normalize_tasting_notes
from gesha.parsers.common import extract_matching_urls, extract_text, parse_price

PRODUCT_URL_PATTERN = re.compile(r"^/collections/coffee/products/[^/?#]+$")


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
        # Match key, colon/dash, then capture until the next known key or end
        pattern = rf"{re.escape(key)}\s*[:\-]\s*(.*?)(?=(?:Farmer|Origin|Process|Varietal|Altitude|Roast level|Size|In the cup|$))"
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            value = match.group(1).strip()
            # Remove line breaks and extra spaces
            value = re.sub(r"\s+", " ", value)
            return value if value else None
        return None

    details["origin"] = value_for("Origin")
    details["producer"] = value_for("Farmer")
    details["process"] = value_for("Process")
    details["varietal"] = value_for("Varietal")
    details["altitude"] = value_for("Altitude")
    details["roast_style"] = value_for("Roast level")
    details["bag_size"] = value_for("Size")
    return details


def _extract_tasting_notes(text: str) -> List[str]:
    match = re.search(r"In the cup\s*:\s*(.*?)(?:\s+(?:In|ABOUT)|$)", text, re.IGNORECASE | re.DOTALL)
    if match:
        return normalize_tasting_notes(re.split(r"[,;/]\s*", match.group(1)))
    return []


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
        origin=normalize_country(details.get("origin")),
        producer=details.get("producer"),
        process=normalize_process(details.get("process")),
        varietal=details.get("varietal"),
        altitude=details.get("altitude"),
        tasting_notes=tasting_notes,
        roast_style=details.get("roast_style"),
        price_cents=price_cents,
        bag_size=details.get("bag_size"),
        url=url,
    )
