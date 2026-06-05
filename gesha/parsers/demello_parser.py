from __future__ import annotations

import json
import re
from typing import List, Optional

from bs4 import BeautifulSoup

from gesha.models.coffee import CoffeeData
from gesha.normalization.normalize import (
    normalize_country,
    normalize_process,
    normalize_tasting_notes,
)
from gesha.parsers.common import extract_matching_urls, extract_text, parse_price

PRODUCT_URL_PATTERN = re.compile(r"^/products/[^/?#]+$")
EXCLUDE_SLUG_KEYWORDS = (
    "starter-kit",
    "instant-coffee",
)


def parse_demello_collection(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls = [
        *extract_matching_urls(
            soup,
            selector="[data-url]",
            attribute="data-url",
            base_url=base_url,
            pattern=PRODUCT_URL_PATTERN,
        ),
        *extract_matching_urls(
            soup,
            selector="a[href^='/products/']",
            attribute="href",
            base_url=base_url,
            pattern=PRODUCT_URL_PATTERN,
        ),
    ]
    urls = [url for url in urls if not any(keyword in url.rsplit("/", 1)[-1].lower() for keyword in EXCLUDE_SLUG_KEYWORDS)]

    return sorted(dict.fromkeys(urls))


def _extract_json_ld_description(soup: BeautifulSoup) -> Optional[str]:
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") in {"Product", "ProductGroup"}:
            description = data.get("description")
            if isinstance(description, str) and description.strip():
                return description.strip()
    return None


def _extract_tasting_notes(description: Optional[str]) -> List[str]:
    if not description:
        return []
    snippet = description.splitlines()[0]
    parts = re.split(r"[·•,;/\\]\s*", snippet)
    return normalize_tasting_notes(parts)


def _find_details_block(soup: BeautifulSoup) -> str:
    for block in soup.select("div.metafield-rich_text_field"):
        text = block.get_text("\n", strip=True)
        if "Country" in text and "Process" in text:
            return text
    return soup.get_text("\n", strip=True)


def _parse_demello_details(text: str) -> dict[str, Optional[str]]:
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
        match = re.search(rf"{re.escape(key)}\s*[:\-]\s*(.*?)(?:\n|$)", text, re.IGNORECASE)
        return match.group(1).strip() if match else None

    details["origin"] = value_for("Country")
    details["producer"] = value_for("Producer")
    details["process"] = value_for("Process")
    details["varietal"] = value_for("Variety")
    details["altitude"] = value_for("Altitude")
    details["bag_size"] = value_for("Size")
    return details


def parse_demello_product(html: str, url: str) -> CoffeeData:
    soup = BeautifulSoup(html, "html.parser")
    title = extract_text(soup.select_one("h1.product__title, h1")) or "Unknown coffee"
    price = extract_text(soup.select_one("span.price-item.price-item--regular"))
    if price is None:
        price = extract_text(soup.select_one("meta[property='og:price:amount']"))
    price_cents = parse_price(price)

    description = _extract_json_ld_description(soup)
    if not description:
        description = extract_text(soup.select_one("div.product__description__content p")) or ""

    details_block = _find_details_block(soup)
    details = _parse_demello_details(details_block)

    return CoffeeData(
        roaster="De Mello Coffee",
        name=title,
        origin=normalize_country(details.get("origin")) or normalize_country(title),
        producer=details.get("producer"),
        process=normalize_process(details.get("process")) or normalize_process(title),
        varietal=details.get("varietal"),
        altitude=details.get("altitude"),
        tasting_notes=_extract_tasting_notes(description),
        roast_style=details.get("roast_style"),
        price_cents=price_cents,
        bag_size=details.get("bag_size"),
        url=url,
    )
