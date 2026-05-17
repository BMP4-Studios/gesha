from __future__ import annotations

import json
import re
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from gesha.models.coffee import CoffeeData
from gesha.normalization.normalize import normalize_country, normalize_process, normalize_tasting_notes

PRODUCT_URL_PATTERN = re.compile(r"^/products/[^/?#]+$")


def parse_demello_collection(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: List[str] = []

    for element in soup.select("[data-url]"):
        href = element.get("data-url")
        if not href:
            continue
        href = href.strip()
        if PRODUCT_URL_PATTERN.match(href):
            urls.append(urljoin(base_url, href))

    for anchor in soup.select("a[href^='/products/']"):
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
    title = _extract_text(soup.select_one("h1.product__title, h1")) or "Unknown coffee"
    price = _extract_text(soup.select_one("span.price-item.price-item--regular"))
    if price is None:
        price = _extract_text(soup.select_one("meta[property='og:price:amount']"))
    price_cents = _parse_price(price)

    description = _extract_json_ld_description(soup)
    if not description:
        description = _extract_text(soup.select_one("div.product__description__content p")) or ""

    details_block = _find_details_block(soup)
    details = _parse_demello_details(details_block)

    return CoffeeData(
        roaster="De Mello Coffee",
        name=title,
        origin=normalize_country(details.get("origin")),
        producer=details.get("producer"),
        process=normalize_process(details.get("process")),
        varietal=details.get("varietal"),
        altitude=details.get("altitude"),
        tasting_notes=_extract_tasting_notes(description),
        roast_style=details.get("roast_style"),
        price_cents=price_cents,
        bag_size=details.get("bag_size"),
        url=url,
    )
