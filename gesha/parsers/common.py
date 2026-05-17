from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup


def extract_text(element: Optional[BeautifulSoup]) -> Optional[str]:
    if element is None:
        return None
    if element.name == "meta":
        content = element.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    text = element.get_text(separator=" ", strip=True)
    return text if text else None


def extract_matching_urls(
    soup: BeautifulSoup,
    *,
    selector: str,
    attribute: str,
    base_url: str,
    pattern: re.Pattern[str],
) -> list[str]:
    urls: list[str] = []
    for element in soup.select(selector):
        href = element.get(attribute)
        if not href:
            continue
        href = href.strip()
        if pattern.match(href):
            urls.append(urljoin(base_url, href))
    return urls


def parse_price(value: str | None) -> Optional[int]:
    if not value:
        return None
    match = re.search(r"(?:CA)?\$\s*([0-9]+(?:\.[0-9]{1,2})?)", value)
    if not match:
        return None
    return int(float(match.group(1)) * 100)
