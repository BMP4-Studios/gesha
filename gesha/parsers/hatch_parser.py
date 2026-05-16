from __future__ import annotations

import re
from typing import List, Optional

from bs4 import BeautifulSoup

from gesha.models.coffee import CoffeeData
from gesha.normalization.normalize import normalize_country, normalize_process, normalize_tasting_notes

PRODUCT_LINK_PATTERN = re.compile(r"/products/")


def parse_hatch_collection(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.find_all("a", href=PRODUCT_LINK_PATTERN)
    urls: List[str] = []
    for anchor in anchors:
        href = anchor.get("href")
        if not href:
            continue
        if href.startswith("http"):
            urls.append(href)
            continue
        urls.append(base_url.rstrip("/") + href)
    return sorted(set(urls))


def _extract_text(element: Optional[BeautifulSoup]) -> Optional[str]:
    if element is None:
        return None
    text = element.get_text(separator=" ", strip=True)
    return text if text else None


def _parse_price(value: str | None) -> Optional[int]:
    if not value:
        return None
    match = re.search(r"\$?\s*([0-9]+(?:\.[0-9]{1,2})?)", value)
    if not match:
        return None
    return int(float(match.group(1)) * 100)


def _collect_details(soup: BeautifulSoup) -> dict[str, Optional[str]]:
    detail_text = "\n".join([tag.get_text(separator=": ", strip=True) for tag in soup.select(".product-description, .product-details, .product-info")])
    details = {
        "origin": None,
        "producer": None,
        "process": None,
        "varietal": None,
        "altitude": None,
        "roast_style": None,
        "bag_size": None,
    }
    if detail_text:
        for line in detail_text.splitlines():
            lower = line.lower()
            if "origin" in lower and ":" in line:
                details["origin"] = line.split(":", 1)[1].strip()
            elif "producer" in lower and ":" in line:
                details["producer"] = line.split(":", 1)[1].strip()
            elif "process" in lower and ":" in line:
                details["process"] = line.split(":", 1)[1].strip()
            elif "variet" in lower and ":" in line:
                details["varietal"] = line.split(":", 1)[1].strip()
            elif "altitude" in lower and ":" in line:
                details["altitude"] = line.split(":", 1)[1].strip()
            elif "roast" in lower and ":" in line:
                details["roast_style"] = line.split(":", 1)[1].strip()
            elif "bag" in lower and ":" in line:
                details["bag_size"] = line.split(":", 1)[1].strip()
    return details


def parse_hatch_product(html: str, url: str) -> CoffeeData:
    soup = BeautifulSoup(html, "html.parser")
    title = _extract_text(soup.select_one("h1, .product-title, .product_name")) or "Unknown coffee"
    price = _extract_text(soup.select_one(".price, .product-price, [data-price]"))
    price_cents = _parse_price(price)

    description = _extract_text(soup.select_one(".product-description, .product-single__description, .description")) or ""
    tasting_notes = []
    note_elements = soup.select(".tasting-notes li, .product-tasting-notes li, .tasting-note")
    if note_elements:
        tasting_notes = [note.get_text(strip=True) for note in note_elements]
    else:
        tasting_notes = re.split(r"[;,\n]", description)

    details = _collect_details(soup)

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
    )
