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
    # 1. Normalize to NFKC form to handle mathematical script (e.g. blossomed) and full-width characters.
    normalized_text = unicodedata.normalize("NFKC", text)
    # 2. Remove characters that are not alphanumeric, whitespace, or common punctuation.
    # This regex keeps letters, numbers, spaces, and common punctuation used in product text/prices.
    cleaned_text = re.sub(r'[^\w\s.,!?"\'#\-:;/$•·]', '', normalized_text)
    # Collapse multiple spaces resulting from removal
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
    """Return deduplicated tasting notes from text or parser candidates."""
    if values is None:
        return []
    if isinstance(values, str):
        # Support standard separators plus bullets, middle dots, and "and/&"
        values = re.split(r"[,;/]|&|\s+and\s+|\s+-\s+|[•·|]|\.\s+", values, flags=re.IGNORECASE)
    normalized: list[str] = []
    # Merge obvious wording variants so flavor searches do not miss matches.
    for note in values:
        candidate = remove_emojis(note.strip().lower()).strip(" .")
        if not candidate:
            continue
        if candidate == "milk chocolate":
            candidate = "chocolate"
        if candidate == "florals":
            candidate = "floral"
        normalized.append(candidate)
    return sorted(dict.fromkeys(normalized))
