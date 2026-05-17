from __future__ import annotations

import re
from typing import Iterable, List

PROCESS_MAP = {
    "fully washed": "washed",
    "washed": "washed",
    "wet process": "washed",
    "natural": "natural",
    "honey": "honey",
    "pulped natural": "honey",
    "anaerobic": "anaerobic",
}

COUNTRY_MAP = {
    "canada": "Canada",
    "costa rica": "Costa Rica",
    "ethiopia": "Ethiopia",
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


def normalize_process(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    return PROCESS_MAP.get(normalized, normalized)


def normalize_country(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    parts = [part.strip() for part in normalized.split(",") if part.strip()]
    candidate = parts[-1].lower() if len(parts) > 1 else normalized.lower()
    if candidate in COUNTRY_MAP:
        return COUNTRY_MAP[candidate]
    for alias, canonical in COUNTRY_MAP.items():
        if alias in normalized.lower():
            return canonical
    return normalized


def normalize_tasting_notes(values: Iterable[str] | str | None) -> List[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = re.split(r"[;,\n]", values)
    normalized: list[str] = []
    for note in values:
        candidate = note.strip().lower()
        if not candidate:
            continue
        for tag in NOTE_TAGS:
            if tag in candidate:
                normalized.append(tag)
                break
        else:
            normalized.append(candidate)
    return sorted(dict.fromkeys(normalized))
