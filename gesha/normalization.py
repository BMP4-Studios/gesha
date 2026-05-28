"""Small normalization rules applied when scraper output becomes catalog data.

Parsers call these functions before creating ``CoffeeData`` so product pages
from different roasters can be listed and filtered consistently.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

NA_LABEL = "[red]NONE[/red]"


def remove_emojis(text: str) -> str:
    """Remove decorative characters that otherwise pollute parsed field values."""
    if not text:
        return ""
    # Normalize to NFKC form to handle mathematical script and full-width chars.
    normalized_text = unicodedata.normalize("NFKC", text)
    # Keep common product punctuation plus mojibake bullet chars seen in fixtures.
    cleaned_text = re.sub(r'[^\w\s.,!?"\'#\-:;/$\u00e2\u20ac\u00a2\u00c2\u00b7]', "", normalized_text)
    return re.sub(r"\s+", " ", cleaned_text).strip()


def normalize_process(value: str | None) -> str | None:
    """Return a searchable process label, merging a few common synonyms."""
    if not value:
        return None
    cleaned = remove_emojis(value).lower().strip()
    if cleaned in {"fully washed", "wet process"}:
        return "washed"
    return cleaned


def normalize_country(value: str | None) -> str | None:
    """Clean an origin field while retaining intentional source capitalization."""
    if not value:
        return None
    cleaned = remove_emojis(value).strip()
    return cleaned.title() if cleaned.islower() else cleaned


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

    notes: list[str] = []
    for note in values:
        candidate = re.sub(r"\s+", " ", note).strip().strip(" .")
        if candidate:
            notes.append(candidate.lower())
    return notes
