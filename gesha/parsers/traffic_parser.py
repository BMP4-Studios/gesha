from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from gesha.models.coffee import CoffeeData
from gesha.normalization.normalize import normalize_country, normalize_process, normalize_tasting_notes

PRODUCT_URL_PATTERN = re.compile(r"^/collections/coffee/products/[^/?#]+$")


def parse_traffic_collection(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: List[str] = []

    for anchor in soup.select("a[href*='/products/']"):
        href = anchor.get("href")
        if not href:
            continue
        href = href.strip()
        if PRODUCT_URL_PATTERN.match(href):
            urls.append(urljoin(base_url, href))

    return sorted(dict.fromkeys(urls))


def _extract_text(element: Optional[BeautifulSoup]) -> Optional[str]:
    if element is None:
        return None
    text = element.get_text(separator=" ", strip=True)
    return text if text else None


def _parse_price(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    match = re.search(r"\$\s*([0-9]+(?:\.[0-9]{1,2})?)", value)
    if not match:
        return None
    return int(float(match.group(1)) * 100)


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
    title = _extract_text(soup.select_one("h1")) or "Unknown coffee"

    price_text = _extract_text(soup.select_one("span[class*='price']"))
    price_cents = _parse_price(price_text)

    desc_div = soup.select_one("div.product-block-description")
    description = _extract_text(desc_div) if desc_div else ""

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
