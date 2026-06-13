"""Reusable HTML/text extraction helpers for roaster-specific parsers.

Individual parsers use these helpers for standard storefront concerns such as
product links, prices, sizes, and labeled product metadata.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from bs4 import BeautifulSoup, Tag

COMMON_TASTING_NOTE_LABELS = [
    "Notes",
    "Tasting Notes",
    "In the cup",
    "Reminds us of",
    "flavour Profile",
    "Flavor Profile",
    "Cup Notes",
    "Profile",
    "Aroma",
]

PRODUCT_FACT_FIELDS = (
    "origin",
    "producer",
    "process",
    "varietal",
    "altitude",
    "roast_style",
    "bag_size",
    "tasting_notes",
)

DEFAULT_PRODUCT_FACT_LABELS: dict[str, tuple[str, ...]] = {
    "origin": ("Origin", "Origins", "Country", "Region", "Place"),
    "producer": ("Producer", "Producers", "Coffee Producers", "Farmer", "Farm"),
    "process": ("Process", "Method"),
    "varietal": ("Varietal", "Variety", "Varieties", "Cultivar"),
    "altitude": ("Altitude", "Elevation"),
    "roast_style": ("Roast Level", "Roast Style", "Roast", "Value / Roasting degree"),
    "bag_size": ("Amount", "Size", "Specs"),
    "tasting_notes": tuple(COMMON_TASTING_NOTE_LABELS),
}

DEFAULT_PRODUCT_FACT_STOP_LABELS = ("About", "Description", "Story")


def _label_pattern(label: str) -> str:
    """Build a regex fragment that tolerates flexible whitespace in labels."""
    return r"\s+".join(re.escape(part) for part in label.strip().split())


def _clean_fact_text(value: str) -> str | None:
    """Collapse whitespace around one extracted product-fact value."""
    cleaned = value.replace("\xa0", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" \t\r\n:-")
    return cleaned or None


def _strip_repeated_label(value: str, labels: Sequence[str]) -> str:
    """Handle duplicated labels such as ``Origin: Origin: Colombia``."""
    cleaned = value
    for label in sorted(labels, key=len, reverse=True):
        pattern = rf"^{_label_pattern(label)}\s*[:\uff1a-]\s*"
        cleaned = re.sub(pattern, "", cleaned, count=1, flags=re.IGNORECASE).strip()
    return cleaned


def _text_from_row(element: Tag) -> str:
    """Extract row-like text while ignoring decorative SVG content."""
    clone = BeautifulSoup(str(element), "html.parser")
    for noisy in clone.select("script, style, noscript, svg"):
        noisy.decompose()
    return clone.get_text(" ", strip=True)


def _is_inside_ignored_tree(element: Tag) -> bool:
    """Return whether an element is nested inside non-content markup."""
    return element.find_parent(["script", "style", "noscript"]) is not None


def extract_labeled_product_facts_from_text(
    text: str | None,
    *,
    label_aliases: Mapping[str, Sequence[str]] | None = None,
    stop_labels: Sequence[str] = DEFAULT_PRODUCT_FACT_STOP_LABELS,
) -> dict[str, str]:
    """Extract ordered ``Label: value`` product facts from a text block."""
    if not text:
        return {}

    aliases = label_aliases or DEFAULT_PRODUCT_FACT_LABELS
    normalized_text = text.replace("\xa0", " ")
    markers: list[tuple[int, int, str | None, str | None]] = []

    # Collect every known label occurrence with its canonical catalog field.
    for field, labels in aliases.items():
        for label in labels:
            pattern = rf"(?<![\w]){_label_pattern(label)}\s*[:\uff1a-]\s*"
            for match in re.finditer(pattern, normalized_text, flags=re.IGNORECASE):
                markers.append((match.start(), match.end(), field, label))

    # Stop labels bound the previous value without becoming facts themselves.
    for label in stop_labels:
        pattern = rf"(?<![\w]){_label_pattern(label)}(?=\s*(?:[:\uff1a-]|\b))"
        for match in re.finditer(pattern, normalized_text, flags=re.IGNORECASE):
            markers.append((match.start(), match.end(), None, None))

    if not markers:
        return {}

    # Prefer the longest non-overlapping label when aliases share words.
    markers.sort(key=lambda marker: (marker[0], -(marker[1] - marker[0])))
    selected: list[tuple[int, int, str | None, str | None]] = []
    occupied_until = -1
    for marker in markers:
        if marker[0] < occupied_until:
            continue
        selected.append(marker)
        occupied_until = marker[1]

    # A value runs from the end of one label to the start of the next marker.
    facts: dict[str, str] = {}
    for index, marker in enumerate(selected):
        field = marker[2]
        if field is None or field in facts:
            continue

        next_start = selected[index + 1][0] if index + 1 < len(selected) else len(normalized_text)
        value = _clean_fact_text(normalized_text[marker[1] : next_start])
        if value is None:
            continue

        value = _strip_repeated_label(value, aliases.get(field, ()))
        value = _clean_fact_text(value)
        if value:
            facts[field] = value

    return facts


def extract_labeled_product_facts_from_html(
    soup: BeautifulSoup | Tag,
    *,
    label_aliases: Mapping[str, Sequence[str]] | None = None,
    stop_labels: Sequence[str] = DEFAULT_PRODUCT_FACT_STOP_LABELS,
) -> dict[str, str]:
    """Extract product facts from repeated labeled rows on a product page."""
    facts: dict[str, str] = {}

    # Merge in catalog-field order so earlier, more local values win.
    def merge(new_values: Mapping[str, str]) -> None:
        for field in PRODUCT_FACT_FIELDS:
            value = new_values.get(field)
            if value and field not in facts:
                facts[field] = value

    # Most Shopify themes render specs as list items, paragraphs, or table rows.
    for row in soup.find_all(["li", "p", "tr"]):
        if not isinstance(row, Tag) or _is_inside_ignored_tree(row):
            continue

        if row.name == "tr":
            cells = row.find_all(["th", "td"], recursive=False)
            if len(cells) >= 2:
                label = _text_from_row(cells[0])
                value = " ".join(_text_from_row(cell) for cell in cells[1:])
                merge(
                    extract_labeled_product_facts_from_text(
                        f"{label}: {value}",
                        label_aliases=label_aliases,
                        stop_labels=stop_labels,
                    )
                )

        # Plain row text handles "Process: Washed" and nested strong/span labels.
        merge(
            extract_labeled_product_facts_from_text(
                _text_from_row(row),
                label_aliases=label_aliases,
                stop_labels=stop_labels,
            )
        )

    # Definition lists show up on a few non-standard product detail sections.
    for term in soup.find_all("dt"):
        if not isinstance(term, Tag) or _is_inside_ignored_tree(term):
            continue
        definition = term.find_next_sibling("dd")
        if not isinstance(definition, Tag):
            continue
        merge(
            extract_labeled_product_facts_from_text(
                f"{_text_from_row(term)}: {_text_from_row(definition)}",
                label_aliases=label_aliases,
                stop_labels=stop_labels,
            )
        )

    # As a fallback, scan larger blocks and only accept ones with multiple facts.
    if len(facts) < 2:
        for block in soup.find_all(["div", "section", "article"]):
            if not isinstance(block, Tag) or _is_inside_ignored_tree(block):
                continue
            block_facts = extract_labeled_product_facts_from_text(
                _text_from_row(block),
                label_aliases=label_aliases,
                stop_labels=stop_labels,
            )
            if len(block_facts) >= 2:
                merge(block_facts)
                break

    return facts
