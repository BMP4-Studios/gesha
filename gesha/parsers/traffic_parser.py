"""Parse Traffic Coffee theme pages for the Traffic scraper adapter.

Traffic uses an HTML description block with labeled fields, so this module
isolates its selectors and extraction choices from generic scraping transport.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from gesha.coffee_data import CoffeeData
from gesha.normalization import normalize_country, normalize_process, normalize_tasting_notes
from gesha.parsers.common import (
    DEFAULT_PRODUCT_FACT_STOP_LABELS,
    extract_labeled_product_facts_from_html,
    extract_labeled_product_facts_from_text,
    extract_matching_urls,
    extract_shopify_bag_size,
    extract_text,
    parse_price,
)

PRODUCT_URL_PATTERN = re.compile(r"^/collections/coffee/products/[^/?#]+$")
DETAIL_STOP_LABELS = (*DEFAULT_PRODUCT_FACT_STOP_LABELS, "ABOUT")


def parse_traffic_collection(html: str, base_url: str) -> list[str]:
    """Extract unique coffee product URLs from Traffic's collection markup."""
    soup = BeautifulSoup(html, "html.parser")
    urls = extract_matching_urls(
        soup,
        selector="a[href*='/products/']",
        attribute="href",
        base_url=base_url,
        pattern=PRODUCT_URL_PATTERN,
    )

    return sorted(dict.fromkeys(urls))


def parse_traffic_product(html: str, url: str) -> CoffeeData:
    """Build one validated catalog item from a Traffic product HTML page."""
    soup = BeautifulSoup(html, "html.parser")
    title = extract_text(soup.select_one("h1")) or "Unknown coffee"

    price_text = extract_text(soup.select_one("span[class*='price']"))
    price_cents = parse_price(price_text)

    # Traffic keeps most useful metadata in a single product description
    # element, allowing shared label extraction for each field.
    desc_div = soup.select_one("div.product-block-description")
    description = extract_text(desc_div) if desc_div else ""
    if description is None:
        description = ""

    details = {}
    if desc_div:
        details = extract_labeled_product_facts_from_html(desc_div, stop_labels=DETAIL_STOP_LABELS)
    if not details:
        details = extract_labeled_product_facts_from_text(description, stop_labels=DETAIL_STOP_LABELS)
    tasting_notes = normalize_tasting_notes(details.get("tasting_notes"))

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
        bag_size=details.get("bag_size") or extract_shopify_bag_size(soup, title, url),
        url=url,
    )
