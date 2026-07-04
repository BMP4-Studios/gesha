"""Coffee bag-weight and unit-price helpers."""

from __future__ import annotations

import re

WEIGHT_PATTERN = re.compile(r"(?<!\w)(\d+(?:\.\d+)?)\s*(kg|g|lb|lbs|oz)\b", re.IGNORECASE)
GRAMS_PER_UNIT = {
    # Normalize every bag size to grams so unit-price comparisons are simple.
    "g": 1.0,
    "kg": 1000.0,
    "oz": 28.349523125,
    "lb": 453.59237,
    "lbs": 453.59237,
}
NON_RETAIL_VARIANT_MARKERS = ("b2b", "wholesale")


def weight_to_grams(value: int | float, unit: str) -> int | None:
    """Convert a positive Shopify weight value to rounded grams."""
    # Shopify can supply weight as a number plus unit, but malformed variants
    # occasionally have missing units or zero weights.
    multiplier = GRAMS_PER_UNIT.get(unit.strip().lower())
    if multiplier is None or value <= 0:
        return None
    return round(float(value) * multiplier)


def parse_weight_grams(value: str | None) -> int | None:
    """Extract the first supported bag weight from free-form variant text."""
    # Variant names often contain the only useful size signal, e.g. "250g Bag".
    if not value:
        return None
    match = WEIGHT_PATTERN.search(value)
    if match is None:
        return None
    return weight_to_grams(float(match.group(1)), match.group(2))


def price_per_100g_cents(price_cents: int | None, weight_grams: int | None) -> int | None:
    """Return a rounded integer-cent price per 100 grams."""
    # Display NONE if we have missing or invalid inputs
    if price_cents is None or weight_grams is None or weight_grams <= 0:
        return None
    return round(price_cents * 100 / weight_grams)


def is_retail_variant(name: str) -> bool:
    """Reject variants explicitly reserved for business or wholesale buyers."""
    # Business-only variants can be huge and cheap per gram, which would distort
    # consumer cart recommendations.
    normalized_name = name.casefold()
    return not any(marker in normalized_name for marker in NON_RETAIL_VARIANT_MARKERS)
