from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List

NA_LABEL = "NONE"

# Processes that are correct as-is
VALID_PROCESSES = {
    "washed",
    "natural",
    "honey",
    "anaerobic",
    "co-ferment",
    "carbonic maceration",
    "experimental",
    "decaf",
    "blend",
}

# Non-standard terms that should map to a valid process
PROCESS_ALIASES = {
    "fully washed": "washed",
    "wet process": "washed",
    "pulped natural": "honey",
    "various": "blend",
}

# Countries/Origins that are correct as-is
VALID_COUNTRIES = {
    "Bolivia",
    "Brazil",
    "Burundi",
    "Canada",
    "Colombia",
    "Costa Rica",
    "Dominican Republic",
    "Ecuador",
    "El Salvador",
    "Ethiopia",
    "Guatemala",
    "Honduras",
    "India",
    "Indonesia",
    "Kenya",
    "Mexico",
    "Myanmar",
    "Nicaragua",
    "Panama",
    "Papua New Guinea",
    "Peru",
    "Rwanda",
    "Tanzania",
    "Thailand",
    "Uganda",
    "Vietnam",
    "Yemen",
}

# Common abbreviations or misspellings for countries
COUNTRY_ALIASES = {
    "png": "Papua New Guinea",
}

NOTE_TAGS = [
    "berry",
    "chocolate",
    "citrus",
    "floral",
    "caramel",
    "nutty",
    "tropical",
    "spice",
    "vanilla",
]


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
    if not value:
        return None
    normalized = value.strip().lower()

    # 1. Check direct aliases
    if normalized in PROCESS_ALIASES:
        return PROCESS_ALIASES[normalized]

    # 2. Check if it's already a valid process
    if normalized in VALID_PROCESSES:
        return normalized

    # 3. Keyword fallback
    for valid in VALID_PROCESSES:
        if valid in normalized:
            return valid
    for alias, canonical in PROCESS_ALIASES.items():
        if alias in normalized:
            return canonical
    return None


def normalize_country(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    lowered = normalized.lower()

    # 1. Check direct aliases
    if lowered in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[lowered]

    # 2. Check if it's a known valid country (case-insensitive check)
    for valid in VALID_COUNTRIES:
        if valid.lower() == lowered:
            return valid

    # 3. Substring check (e.g., "Western Ethiopia" -> "Ethiopia")
    for valid in VALID_COUNTRIES:
        if valid.lower() in lowered:
            return valid

    # Fallback to last part if comma-separated
    parts = [part.strip() for part in normalized.split(",") if part.strip()]
    if len(parts) > 1:
        return normalize_country(parts[-1])

    return None


def normalize_tasting_notes(values: Iterable[str] | str | None) -> List[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = re.split(r"[;,\n•·|]|\.\s+", values)
    normalized: list[str] = []
    for note in values:
        candidate = remove_emojis(note.strip().lower())
        if not candidate:
            continue
        for tag in NOTE_TAGS:
            if tag in candidate:
                normalized.append(tag)
                break
        else:
            normalized.append(candidate)
    return sorted(dict.fromkeys(normalized))
