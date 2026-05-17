from __future__ import annotations

import json
import re
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from gesha.models.coffee import CoffeeData
from gesha.normalization.normalize import normalize_country, normalize_process, normalize_tasting_notes
from gesha.parsers.common import extract_text, parse_price

PRODUCT_LINK_PATTERN = re.compile(r"^/shop/[^/]+$")
EXCLUDE_PATHS = (
    "/shop/tag/",
    "/shop/subscribe",
    "/shop/workshop",
    "/shop/wholesale",
    "/shop/faq",
    "/shop/blog",
    "/shop/brew-guides",
    "/shop/knowledge",
    "/shop/concentrate",
    "/shop/peak-series",
    "/shop/where-to-buy",
    "/shop/contact",
    "/shop/about",
    "/shop/hatchlings-membership",
    "/shop/RS-sub",
    "/shop/foundation-coffee-subscription",
)


def parse_hatch_collection(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: List[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href.startswith("/shop/"):
            continue
        if any(href.startswith(prefix) for prefix in EXCLUDE_PATHS):
            continue
        if not PRODUCT_LINK_PATTERN.match(href):
            continue
        urls.append(urljoin(base_url, href))
    return sorted(set(urls))


def _decode_embedded_html(html: str) -> Optional[str]:
    pattern = re.compile(r'self\.__next_f\.push\(\[1,"(?P<html>(?:\\.|[^"\\])*)"\]\)')
    for match in pattern.finditer(html):
        raw = match.group("html")
        try:
            decoded = json.loads(f'"{raw}"')
        except json.JSONDecodeError:
            decoded = raw.encode("utf-8").decode("unicode_escape")
        if "Origin:" in decoded or "Reminds us of:" in decoded:
            return decoded
    return None


def _collect_details(raw_html: str) -> dict[str, Optional[str]]:
    details = {
        "origin": None,
        "producer": None,
        "process": None,
        "varietal": None,
        "altitude": None,
        "roast_style": None,
        "bag_size": None,
    }
    detail_text = raw_html.replace("\r", "\n")

    def _find(pattern: str) -> Optional[str]:
        match = re.search(pattern, detail_text, re.IGNORECASE | re.DOTALL)
        return match.group(1).strip() if match else None

    details["origin"] = _find(r"Origin:\s*(.*?)(?:Producer:|Varieties?:|Process:|Elevation:|Harvest:|Recommended Brew:|Reminds us of:|$)")
    details["producer"] = _find(r"Producer:\s*(.*?)(?:Varieties?:|Process:|Elevation:|Harvest:|Recommended Brew:|Reminds us of:|$)")
    details["varietal"] = _find(r"Varieties?:\s*(.*?)(?:Process:|Elevation:|Harvest:|Recommended Brew:|Reminds us of:|$)")
    details["process"] = _find(r"Process:\s*(.*?)(?:Elevation:|Harvest:|Recommended Brew:|Reminds us of:|$)")
    details["altitude"] = _find(r"Elevation:\s*(.*?)(?:Harvest:|Recommended Brew:|Reminds us of:|$)")
    details["bag_size"] = _find(r"(\d+\s*(?:g|kg|oz|lb|bag))")
    return details


def _extract_description(soup: BeautifulSoup) -> str:
    paragraphs = [tag.get_text(" ", strip=True) for tag in soup.find_all("p")]
    for paragraph in paragraphs:
        if any(label in paragraph for label in ["Origin:", "Producer:", "Varieties:", "Process:", "Elevation:", "Harvest:", "Recommended Brew:", "Reminds us of:"]):
            continue
        if paragraph:
            return paragraph
    return ""


def _extract_tasting_notes(raw_html: str) -> List[str]:
    match = re.search(r"Reminds us of:\s*(.*?)(?:$)", raw_html, re.IGNORECASE | re.DOTALL)
    if match:
        return [note.strip() for note in re.split(r"[,;\n]", match.group(1)) if note.strip()]
    return []


def _extract_availability(html: str) -> bool:
    lowered = html.lower()
    if "sold out" in lowered or "out of stock" in lowered or "unavailable" in lowered:
        return False
    return True


def parse_hatch_product(html: str, url: str) -> CoffeeData:
    soup = BeautifulSoup(html, "html.parser")
    title = extract_text(soup.select_one("h1")) or "Unknown coffee"

    embedded_html = _decode_embedded_html(html)
    details_html = embedded_html if embedded_html else html
    detail_soup = BeautifulSoup(details_html, "html.parser")

    price_text = detail_soup.find(text=re.compile(r"CA\$\s*[0-9]+(?:\.[0-9]{1,2})?"))
    if price_text is None:
        price_text = soup.find(text=re.compile(r"CA\$\s*[0-9]+(?:\.[0-9]{1,2})?"))
    price = price_text.strip() if price_text else None
    price_cents = parse_price(price)

    description = _extract_description(detail_soup)
    if not description:
        meta_description = soup.find("meta", {"name": "description"})
        description = meta_description.get("content", "") if meta_description else ""

    raw_html = detail_soup.get_text("\n", strip=True)
    details = _collect_details(raw_html)
    tasting_notes = _extract_tasting_notes(raw_html)
    if not tasting_notes:
        tasting_notes = re.split(r"[,;\n]", description)

    return CoffeeData(
        roaster="Hatch Coffee",
        name=title,
        origin=normalize_country(details.get("origin")),
        producer=details.get("producer"),
        process=normalize_process(details.get("process")),
        varietal=details.get("varietal"),
        altitude=details.get("altitude"),
        tasting_notes=normalize_tasting_notes(tasting_notes),
        roast_style=details.get("roast_style"),
        price_cents=price_cents,
        bag_size=details.get("bag_size"),
        url=url,
        availability=_extract_availability(html),
    )
