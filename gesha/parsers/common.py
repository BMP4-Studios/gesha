from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from gesha.normalization.normalize import remove_emojis

COMMON_TASTING_NOTE_LABELS = [
    "Notes",
    "Tasting Notes",
    "In the cup",
    "Reminds us of",
    "Flavor Profile",
    "Profile",
    "Aroma",
]


def extract_text(element: Optional[BeautifulSoup]) -> Optional[str]:
    if element is None:
        return None
    if element.name == "meta":
        content = element.get("content")
        if isinstance(content, str) and content.strip():
            return remove_emojis(content.strip()) or None
    text = element.get_text(separator=" ", strip=True)
    if not text:
        return None
    return remove_emojis(text) or None


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


def extract_labeled_value(text: str, labels: list[str], stop_labels: list[str]) -> Optional[str]:
    label_pattern = "|".join(re.escape(label) for label in labels)
    stop_pattern = "|".join(re.escape(label) for label in stop_labels)
    pattern = rf"(?:{label_pattern})\s*[:\-]\s*(.*?)(?=\n|(?:{stop_pattern})(?:\s*[:\-]|\b)|$)"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    value = re.sub(r"\s+", " ", match.group(1)).strip()
    for label in labels:
        value = re.sub(rf"^{re.escape(label)}\s*[:\-]\s*", "", value, flags=re.IGNORECASE).strip()
    return value if value else None


def clean_tasting_note_candidates(values: list[str]) -> list[str]:
    notes: list[str] = []
    prose_words = {
        "a",
        "an",
        "around",
        "but",
        "can",
        "for",
        "from",
        "if",
        "in",
        "it",
        "it's",
        "of",
        "on",
        "or",
        "our",
        "should",
        "shouldn't",
        "that",
        "the",
        "this",
        "throughout",
        "to",
        "very",
        "we",
        "with",
        "you",
        "your",
    }
    noisy_fragments = (
        "{",
        "}",
        "[",
        "]",
        '"',
        "$",
        "amount:",
        "createdat",
        "updatedat",
        "metadata",
        "price",
        "variant",
        "shipping",
        "description:",
        "order details",
        "producer:",
        "origin:",
        "process:",
        "variety:",
        "varietal:",
        "altitude:",
        "afford",
        "amp",
        "coffee.",
        "delicious coffee",
        "family",
        "farm",
        "farmer:",
        "grown",
        "history",
        "experience",
        "shading",
        "shade",
        "farming",
        "laboratory",
        "rewarding",
        "seasons",
        "year",
    )
    noisy_exact = {
        "go",
        "santa bárbara",
    }
    for value in values:
        note = re.sub(r"\s+", " ", value).strip(" .")
        note = re.sub(r"^and\s+", "", note, flags=re.IGNORECASE).strip()
        lowered = note.lower()
        if not note:
            continue
        if lowered in noisy_exact:
            continue
        words = re.findall(r"[a-z']+", lowered)
        if len(note) > 48 or len(note.split()) > 4:
            continue
        if note[0] in "),.:;!?":
            continue
        if any(char in note for char in ".!?"):
            continue
        if any(word.replace("’", "'") in prose_words for word in words):
            continue
        if any(fragment in lowered for fragment in noisy_fragments):
            continue
        notes.append(note)
    return notes
