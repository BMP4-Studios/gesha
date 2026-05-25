"""Parse Hatch's application-rendered shop pages into catalog records.

Hatch is registered as an opt-in scraper because its Next.js-like payload can
place product details in encoded page data rather than plain visible HTML.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

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
    """Decide whether a Hatch shop path appears to sell roasted coffee."""
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


def parse_hatch_collection(html: str, base_url: str) -> list[str]:
    """Discover coffee links in visible markup and embedded application data."""
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href")
        if not isinstance(href, str):
            continue
        href = href.strip()
        if _is_hatch_product_path(href):
            urls.append(urljoin(base_url, href))

    # Client-rendered pages may serialize links into escaped script payloads.
    for raw_path in re.findall(r"(?:href=|href\\?\":\\?\")(?P<path>\\?/shop\\?/[^\"\\?#]+)", html):
        href = raw_path.replace("\\/", "/")
        if _is_hatch_product_path(href):
            urls.append(urljoin(base_url, href))

    for raw_path in re.findall(r"/shop/[^\"'?#<> )]+", html):
        href = raw_path.replace("\\/", "/").rstrip("\\")
        if _is_hatch_product_path(href):
            urls.append(urljoin(base_url, href))

    return sorted(set(urls))


def _decode_embedded_html(html: str) -> str | None:
    """Decode a serialized page fragment containing Hatch product metadata."""
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


def _collect_details(raw_html: str) -> dict[str, str | None]:
    """Collect labeled detail fields from decoded or ordinary product text."""
    details: dict[str, str | None] = {
        "origin": None,
        "producer": None,
        "process": None,
        "varietal": None,
        "altitude": None,
        "roast_style": None,
        "bag_size": None,
    }
    detail_text = raw_html.replace("\r", "\n")

    def _find(pattern: str, label: str) -> str | None:
        """Search one Hatch detail span and strip any repeated label text."""
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
    """Return descriptive copy while skipping structured detail paragraphs."""
    paragraphs = [tag.get_text(" ", strip=True) for tag in soup.find_all("p")]
    for paragraph in paragraphs:
        if any(label in paragraph for label in ["Origin:", "Producer:", "Varieties:", "Process:", "Elevation:", "Harvest:", "Recommended Brew:", "Reminds us of:"]):
            continue
        if paragraph:
            return paragraph
    return ""


def _extract_tasting_notes(raw_html: str) -> list[str]:
    """Read and sanitize Hatch's ``Reminds us of`` or ``Notes`` value."""
    value = extract_labeled_value(raw_html, ["Reminds us of", "Notes"], DETAIL_LABELS)
    if not value:
        return []
    return clean_tasting_note_candidates(re.split(r"[,;\n|]|\s+-\s+", value))


def _extract_availability(html: str) -> bool:
    """Infer whether the storefront exposes the product as purchasable."""
    lowered = html.lower()
    if "sold out" in lowered or "out of stock" in lowered or "unavailable" in lowered:
        return False
    return True


def parse_hatch_product(html: str, url: str) -> CoffeeData:
    """Build a catalog item from Hatch HTML and any decoded page payload."""
    soup = BeautifulSoup(html, "html.parser")
    title = extract_text(soup.select_one("h1")) or "Unknown coffee"

    # Metadata is frequently embedded in framework hydration data rather than
    # the initially visible page. Use it when detected, otherwise parse HTML.
    embedded_html = _decode_embedded_html(html)
    details_html = embedded_html if embedded_html else html
    detail_soup = BeautifulSoup(details_html, "html.parser")

    price_text = detail_soup.find(string=re.compile(r"CA\$\s*[0-9]+(?:\.[0-9]{1,2})?"))
    if price_text is None:
        price_text = soup.find(string=re.compile(r"CA\$\s*[0-9]+(?:\.[0-9]{1,2})?"))
    price = price_text.strip() if price_text else None
    price_cents = parse_price(price)

    # Prefer actual product copy, with metadata description as a fallback for
    # sparse server-rendered pages.
    description = _extract_description(detail_soup)
    if not description:
        meta_description = soup.find("meta", {"name": "description"})
        if isinstance(meta_description, Tag):
            content = meta_description.get("content", "")
            description = content if isinstance(content, str) else ""

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
