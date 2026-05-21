from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List

NA_LABEL = "*** NONE ***"

def remove_emojis(text: str) -> str:
    """Remove emojis, symbols, and non-standard decorative characters from text."""
    if not text:
        return ""
    # 1. Normalize to NFKC form to handle mathematical script (e.g. blossomed) and full-width characters.
    normalized_text = unicodedata.normalize("NFKC", text)
    # 2. Remove characters that are not alphanumeric, whitespace, or common punctuation.
    # This regex keeps letters, numbers, spaces, and the following punctuation: . , ! ? ' " - # : ; /
    cleaned_text = re.sub(r'[^\w\s.,!?"\'#\-:;/]', '', normalized_text)
    # Collapse multiple spaces resulting from removal
    return re.sub(r"\s+", " ", cleaned_text).strip()


def normalize_process(value: str | None) -> str | None:
    """Bare minimum normalization: lowercase and strip."""
    if not value:
        return None
    return remove_emojis(value).lower().strip()


def normalize_country(value: str | None) -> str | None:
    """Bare minimum normalization: lowercase and strip."""
    if not value:
        return None
    return remove_emojis(value).lower().strip()


def normalize_tasting_notes(values: Iterable[str] | str | None) -> List[str]:
    """Split by common delimiters and lowercase each note."""
    if values is None:
        return []
    if isinstance(values, str):
        # Support standard separators plus bullets, middle dots, and "and/&"
        values = re.split(r"[,;/]|&|\s+and\s+|\s+-\s+|[•·|]|\.\s+", values, flags=re.IGNORECASE)
    normalized: list[str] = []
    for note in values:
        candidate = remove_emojis(note.strip().lower())
        if not candidate:
            continue
        normalized.append(candidate)
    return sorted(dict.fromkeys(normalized))
