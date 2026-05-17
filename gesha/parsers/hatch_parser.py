from __future__ import annotations

import json
import re
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from gesha.models.coffee import CoffeeData
from gesha.normalization.normalize import normalize_country, normalize_process, normalize_tasting_notes
from gesha.parsers.common import clean_tasting_note_candidates, extract_labeled_value, extract_text, parse_price

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
EXCLUDE_SLUG_KEYWORDS = (
    "apax",
    "berry-jam",
    "beer",
    "book",
    "cold-brew",
    "cold-shots",
    "concentrate",
    "cup",
    "filter",
    "german-bock",
    "hiflux",
    "ipa",
    "kalita",
    "mazagran",
    "mini-cans",
    "nitro",
    "non-alcoholic",
    "oatside",
    "sibarist",
    "tee",
    "third-wave-water",
    "water",
)
DETAIL_LABELS = [
    "Origin",
    "Producer",
    "Variety",
    "Varieties",
    "Process",
    "Elevation",
    "Harvest",
    "Recommended Brew",
    "Reminds us of",
    "Notes",
    "Order Details",
    "Description",
]


def _is_hatch_product_path(path: str) -> bool:
    if not path.startswith("/shop/"):
        return False
    if any(path.startswith(prefix) for prefix in EXCLUDE_PATHS):
        return False
    if not PRODUCT_LINK_PATTERN.match(path):
        return False
    slug = path.rsplit("/", 1)[-1].lower()
    if any(keyword in slug for keyword in EXCLUDE_SLUG_KEYWORDS):
        return False
    return True


def parse_hatch_collection(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: List[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if _is_hatch_product_path(href):
            urls.append(urljoin(base_url, href))

    for raw_path in re.findall(r"(?:href=|href\\?\":\\?\")(?P<path>\\?/shop\\?/[^\"\\?#]+)", html):
        href = raw_path.replace("\\/", "/")
        if _is_hatch_product_path(href):
            urls.append(urljoin(base_url, href))

    for raw_path in re.findall(r"/shop/[^\"'?#<> )]+", html):
        href = raw_path.replace("\\/", "/").rstrip("\\")
        if _is_hatch_product_path(href):
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

    def _find(pattern: str, label: str) -> Optional[str]:
        match = re.search(pattern, detail_text, re.IGNORECASE | re.DOTALL)
        if not match:
            return None
        value = match.group(1).strip()
        value = re.sub(rf"^{re.escape(label)}\s*[:\-]\s*", "", value, flags=re.IGNORECASE).strip()
        return value if value else None

    details["origin"] = _find(r"Origin:\s*(.*?)(?:Producer:|Varieties?:|Process:|Elevation:|Harvest:|Recommended Brew:|Reminds us of:|$)", "Origin")
    details["producer"] = _find(r"Producer:\s*(.*?)(?:Varieties?:|Process:|Elevation:|Harvest:|Recommended Brew:|Reminds us of:|$)", "Producer")
    details["varietal"] = _find(r"Varieties?:\s*(.*?)(?:Process:|Elevation:|Harvest:|Recommended Brew:|Reminds us of:|$)", "Variety")
    details["process"] = _find(r"Process:\s*(.*?)(?:Elevation:|Harvest:|Recommended Brew:|Reminds us of:|$)", "Process")
    details["altitude"] = _find(r"Elevation:\s*(.*?)(?:Harvest:|Recommended Brew:|Reminds us of:|$)", "Elevation")
    details["bag_size"] = _find(r"(\d+\s*(?:g|kg|oz|lb|bag))", "")
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
    value = extract_labeled_value(raw_html, ["Reminds us of", "Notes"], DETAIL_LABELS)
    if not value:
        return []
    return clean_tasting_note_candidates(re.split(r"[,;\n|]|\s+-\s+", value))


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

    price_text = detail_soup.find(string=re.compile(r"CA\$\s*[0-9]+(?:\.[0-9]{1,2})?"))
    if price_text is None:
        price_text = soup.find(string=re.compile(r"CA\$\s*[0-9]+(?:\.[0-9]{1,2})?"))
    price = price_text.strip() if price_text else None
    price_cents = parse_price(price)

    description = _extract_description(detail_soup)
    if not description:
        meta_description = soup.find("meta", {"name": "description"})
        description = meta_description.get("content", "") if meta_description else ""

    raw_html = detail_soup.get_text("\n", strip=True)
    details = _collect_details(raw_html)
    tasting_notes = _extract_tasting_notes(raw_html)

    return CoffeeData(
        roaster="Hatch Coffee",
        name=title,
        origin=normalize_country(details.get("origin")) or normalize_country(title),
        producer=details.get("producer"),
        process=normalize_process(details.get("process")) or normalize_process(title),
        varietal=details.get("varietal"),
        altitude=details.get("altitude"),
        tasting_notes=normalize_tasting_notes(tasting_notes),
        roast_style=details.get("roast_style"),
        price_cents=price_cents,
        bag_size=details.get("bag_size"),
        url=url,
        availability=_extract_availability(html),
    )
