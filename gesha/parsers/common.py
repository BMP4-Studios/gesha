"""Reusable HTML/text extraction helpers for roaster-specific parsers.

Individual parsers use these helpers for standard storefront concerns such as
product links, prices, sizes, and labeled product metadata.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from bs4 import BeautifulSoup, Tag

COMMON_TASTING_NOTE_LABELS = [
    # Roasters use different labels for the same catalog field.
    "Notes",
    "Tasting Notes",
    "Taste Notes",
    "Taste",
    "Impressions",
    "In the cup",
    "Reminds us of",
    "flavour Profile",
    "Flavor Profile",
    "Profile Notes",
    "Cup Notes",
    "Profile",
    "Aroma",
]

PRODUCT_FACT_FIELDS = (
    # Merge order for extracted facts. Earlier names are checked first when
    # combining multiple parse passes from the same HTML section.
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
    # Map normalized catalog fields to the storefront labels that may describe them.
    "origin": ("Origin", "Origins", "Country", "Region", "Place", "Location"),
    "producer": ("Producer", "Producers", "Coffee Producers", "Farmer", "Farm"),
    "process": ("Process", "Method", "Drying Method"),
    "varietal": ("Varietal", "Variety", "Varieties", "Cultivar"),
    "altitude": ("Altitude", "Elevation"),
    "roast_style": ("Roast Level", "Roast Style", "Roast Degree", "Roast", "Value / Roasting degree"),
    "bag_size": ("Amount", "Size", "Specs"),
    "tasting_notes": tuple(COMMON_TASTING_NOTE_LABELS),
}

DEFAULT_PRODUCT_FACT_STOP_LABELS = (
    "About",
    "Description",
    "Story",
    "Importer",
    "Import Partner",
    "Partner Importer",
    "Export Partner",
    "Best After",
)


def _label_pattern(label: str) -> str:
    """Build a regex fragment that tolerates flexible whitespace in labels."""
    # Split/rejoin means "Tasting Notes" matches labels with tabs or line breaks.
    return r"\s+".join(re.escape(part) for part in label.strip().split())


def _clean_fact_text(value: str) -> str | None:
    """Collapse whitespace around one extracted product-fact value."""
    # Non-breaking spaces are common in Shopify rich text.
    cleaned = value.replace("\xa0", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" \t\r\n:-•·")
    return cleaned or None


def _strip_repeated_label(value: str, labels: Sequence[str]) -> str:
    """Handle duplicated labels such as ``Origin: Origin: Colombia``."""
    cleaned = value

    # Longest-first avoids removing "Notes" before "Tasting Notes".
    for label in sorted(labels, key=len, reverse=True):
        pattern = rf"^{_label_pattern(label)}\s*[:\uff1a-]\s*"
        cleaned = re.sub(pattern, "", cleaned, count=1, flags=re.IGNORECASE).strip()
    return cleaned


def _text_from_row(element: Tag) -> str:
    """Extract row-like text while ignoring decorative SVG content."""
    # Work on a clone so removing noisy markup does not mutate the caller's soup.
    clone = BeautifulSoup(str(element), "html.parser")

    # SVG icons and scripts often sit inside spec rows but are not product facts.
    for noisy in clone.select("script, style, noscript, svg"):
        noisy.decompose()
    return clone.get_text(" ", strip=True)


def _is_inside_ignored_tree(element: Tag) -> bool:
    """Return whether an element is nested inside non-content markup."""
    # BeautifulSoup can find nested tags inside script/style blocks; skip them.
    return element.find_parent(["script", "style", "noscript"]) is not None


def _field_for_exact_label(label: str, aliases: Mapping[str, Sequence[str]]) -> tuple[str, int] | None:
    """Map a standalone label node such as ``Origin`` to a catalog field."""
    cleaned = _clean_fact_text(label)
    if cleaned is None:
        return None

    # These sibling-pair labels do not include punctuation, so only exact
    # case-insensitive matches are safe enough to accept.
    normalized = re.sub(r"\s+", " ", cleaned).casefold()
    for field, labels in aliases.items():
        for priority, alias in enumerate(labels):
            alias_normalized = re.sub(r"\s+", " ", alias.strip()).casefold()
            if normalized == alias_normalized:
                return field, priority
    return None


def _next_non_empty_sibling(element: Tag) -> Tag | None:
    """Return the next sibling tag that carries visible text."""
    sibling = element.next_sibling
    while sibling is not None:
        if isinstance(sibling, Tag) and not _is_inside_ignored_tree(sibling):
            if _text_from_row(sibling):
                return sibling
        sibling = sibling.next_sibling
    return None


def extract_labeled_product_facts_from_text(
    text: str | None,
    *,
    label_aliases: Mapping[str, Sequence[str]] | None = None,
    stop_labels: Sequence[str] = DEFAULT_PRODUCT_FACT_STOP_LABELS,
) -> dict[str, str]:
    """Extract ordered ``Label: value`` product facts from a text block."""
    # Empty descriptions or HTML blocks simply have no structured facts.
    if not text:
        return {}

    aliases = label_aliases or DEFAULT_PRODUCT_FACT_LABELS
    normalized_text = text.replace("\xa0", " ")
    markers: list[tuple[int, int, str | None, str | None]] = []

    # Collect every known label occurrence with its canonical catalog field.
    for field, labels in aliases.items():
        for label in labels:
            # The negative lookbehind avoids matching labels in the middle of words.
            pattern = rf"(?<![\w]){_label_pattern(label)}\s*[:\uff1a-]\s*"
            for match in re.finditer(pattern, normalized_text, flags=re.IGNORECASE):
                markers.append((match.start(), match.end(), field, label))

    # Stop labels bound the previous value without becoming facts themselves.
    for label in stop_labels:
        # Stop markers do not need a colon; headings like "About" still end the
        # previous fact section.
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
        # Skip shorter aliases that overlap a longer selected alias.
        if marker[0] < occupied_until:
            continue
        selected.append(marker)
        occupied_until = marker[1]

    # A value runs from the end of one label to the start of the next marker.
    facts: dict[str, str] = {}
    for index, marker in enumerate(selected):
        field = marker[2]
        # Stop markers and duplicate fields are boundaries, not new fact values.
        if field is None or field in facts:
            continue

        next_start = selected[index + 1][0] if index + 1 < len(selected) else len(normalized_text)
        value = _clean_fact_text(normalized_text[marker[1] : next_start])
        if value is None:
            continue

        # Some themes repeat the label at the start of the extracted value.
        value = _strip_repeated_label(value, aliases.get(field, ()))
        value = _clean_fact_text(value)
        if value:
            facts[field] = value

    return facts


def _extract_labeled_fact_from_loose_row_text(
    text: str,
    *,
    label_aliases: Mapping[str, Sequence[str]],
) -> dict[str, str]:
    """Extract one ``Label value`` fact from a compact spec row."""
    # Shogun-style rows sometimes omit punctuation but still start with a known
    # label, such as "Region     Chelbesa, Gedeb". Keep this row-only so prose
    # paragraphs that merely mention a label are not treated as specs.
    cleaned = _clean_fact_text(text)
    if cleaned is None:
        return {}

    for field, labels in label_aliases.items():
        for label in sorted(labels, key=len, reverse=True):
            pattern = rf"^{_label_pattern(label)}\s+(.+)$"
            match = re.match(pattern, cleaned, flags=re.IGNORECASE)
            if not match:
                continue

            value = _clean_fact_text(match.group(1))
            if value:
                return {field: value}
    return {}


def extract_labeled_product_facts_from_html(
    soup: BeautifulSoup | Tag,
    *,
    label_aliases: Mapping[str, Sequence[str]] | None = None,
    stop_labels: Sequence[str] = DEFAULT_PRODUCT_FACT_STOP_LABELS,
) -> dict[str, str]:
    """Extract product facts from repeated labeled rows on a product page."""
    facts: dict[str, str] = {}
    aliases = label_aliases or DEFAULT_PRODUCT_FACT_LABELS

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
            # Table rows usually split label/value into separate cells.
            cells = row.find_all(["th", "td"], recursive=False)
            if len(cells) >= 2:
                label = _text_from_row(cells[0])
                value = " ".join(_text_from_row(cell) for cell in cells[1:])
                merge(
                    extract_labeled_product_facts_from_text(
                        f"{label}: {value}",
                        label_aliases=aliases,
                        stop_labels=stop_labels,
                    )
                )

        row_text = _text_from_row(row)

        # Plain row text handles "Process: Washed" and nested strong/span labels.
        merge(
            extract_labeled_product_facts_from_text(
                row_text,
                label_aliases=aliases,
                stop_labels=stop_labels,
            )
        )

        # Some product builders render spec rows as "Region     Colombia"
        # without punctuation. Limit this to row elements, not whole sections.
        merge(_extract_labeled_fact_from_loose_row_text(row_text, label_aliases=aliases))

    # Definition lists show up on a few non-standard product detail sections.
    for term in soup.find_all("dt"):
        if not isinstance(term, Tag) or _is_inside_ignored_tree(term):
            continue
        # Pair each ``dt`` with its following ``dd`` value.
        definition = term.find_next_sibling("dd")
        if not isinstance(definition, Tag):
            continue
        merge(
            extract_labeled_product_facts_from_text(
                f"{_text_from_row(term)}: {_text_from_row(definition)}",
                label_aliases=aliases,
                stop_labels=stop_labels,
            )
        )

    # Some themes render specs as adjacent bare nodes:
    # <div>Origin</div><div>Colombia</div>. Exact label matching keeps this
    # generic without turning every neighboring div into a product fact.
    sibling_pair_facts: dict[str, tuple[int, str]] = {}
    for label_node in soup.find_all(["div", "span"]):
        if not isinstance(label_node, Tag) or _is_inside_ignored_tree(label_node):
            continue

        field_match = _field_for_exact_label(_text_from_row(label_node), aliases)
        if field_match is None:
            continue

        field, priority = field_match
        if field in facts:
            continue

        value_node = _next_non_empty_sibling(label_node)
        if value_node is None:
            continue

        value = _clean_fact_text(_text_from_row(value_node))
        if not value:
            continue

        # If a theme exposes both "Farm" and "Producer", prefer the alias that
        # appears earlier in DEFAULT_PRODUCT_FACT_LABELS for that catalog field.
        current_value = sibling_pair_facts.get(field)
        if current_value is None or priority < current_value[0]:
            sibling_pair_facts[field] = (priority, value)
    merge({field: value for field, (_, value) in sibling_pair_facts.items()})

    # As a fallback, scan larger blocks and only accept ones with multiple facts.
    # This can fill fields missed by sibling-pair markup, such as labels whose
    # value sits outside the label node's immediate sibling chain.
    if len(facts) < len(PRODUCT_FACT_FIELDS):
        # When a source selector points directly at a metadata container, the
        # selected container itself may carry the complete label/value text.
        block_candidates: list[Tag] = []
        if isinstance(soup, Tag) and soup.name in ("div", "section", "article"):
            block_candidates.append(soup)
        block_candidates.extend(soup.find_all(["div", "section", "article"]))

        for block in block_candidates:
            if not isinstance(block, Tag) or _is_inside_ignored_tree(block):
                continue
            # Requiring multiple facts prevents random marketing copy from being
            # treated as structured metadata.
            block_facts = extract_labeled_product_facts_from_text(
                _text_from_row(block),
                label_aliases=aliases,
                stop_labels=stop_labels,
            )
            if len(block_facts) >= 2:
                merge(block_facts)
                break

    return facts
