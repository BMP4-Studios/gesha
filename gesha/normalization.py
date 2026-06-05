"""Small normalization rules applied when scraper output becomes catalog data.

Parsers call these functions before creating ``CoffeeData`` so product pages
from different roasters can be listed and filtered consistently.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

NA_LABEL = "[red]NONE[/red]"


def normalize_search_text(value: str | None) -> str | None:
    """Remove decorative characters without changing meaningful casing."""
    if not value:
        return None

    # Normalize to NFKC form to handle mathematical script and full-width chars.
    normalized_text = unicodedata.normalize("NFKC", value)

    # Keep common product punctuation plus mojibake bullet chars seen in fixtures.
    cleaned_text = re.sub(r'[^\w\s.,!?"\'#\-:;/$|\u00e2\u20ac\u00a2\u00c2\u00b7]', "", normalized_text)
    return re.sub(r"\s+", " ", cleaned_text).lower().strip()


def price_display(price_cents: int | None) -> str:
    """Render optional integer-cent prices for user-facing output."""
    return f"${price_cents / 100:.2f}" if price_cents is not None else NA_LABEL


def normalize_tasting_notes(values: Iterable[str] | str | None) -> list[str]:
    """Return source-ordered tasting notes in lowercase."""
    if values is None:
        return []
    if isinstance(values, str):
        # Support common note-list separators without reordering source values.
        values = re.split(
            r"[,;/+|]|&|\s+and\s+|\s+-\s+|[\u00e2\u20ac\u00a2\u00c2\u00b7\u2022\u00b7]|\.\s+",
            values,
            flags=re.IGNORECASE,
        )

    # Keep non-empty notes in the same order the roaster presented them.
    notes: list[str] = []
    for note in values:
        if not isinstance(note, str):
            continue
        candidate = re.sub(r"\s+", " ", note).strip().strip(" .")
        if candidate:
            notes.append(candidate.lower())
    return notes
