"""Explainable keyword matching and free-shipping cart optimization."""

from __future__ import annotations

import itertools
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from gesha.db.models import Coffee, CoffeeVariant
from gesha.measurements import is_retail_variant, price_per_100g_cents
from gesha.shipping import Destination

DEFAULT_PREFERENCE_KEYWORDS = (
    "natural",
    "anaerobic",
    "co-ferment",
    "coferment",
    "fermentation",
    "fruit",
    "berry",
    "cherry",
    "peach",
    "mango",
    "pineapple",
    "tropical",
    "wine",
    "funky",
)


@dataclass(frozen=True)
class PreferenceConfig:
    """Keywords and optional destination directives read from a text file."""

    keywords: tuple[str, ...]
    province: str | None = None
    postal_code: str | None = None


@dataclass(frozen=True)
class CartItem:
    """One smallest-bag coffee variant eligible for optimization."""

    coffee_id: int
    roaster_name: str
    name: str
    product_url: str
    variant_id: str | None
    variant_name: str
    bag_size: str
    weight_grams: int
    price_cents: int
    price_per_100g_cents: int
    matched_keywords: tuple[str, ...]


@dataclass(frozen=True)
class CartCandidate:
    """A ranked combination of distinct coffees from one roaster."""

    items: tuple[CartItem, ...]
    subtotal_cents: int
    threshold_cents: int
    matched_keywords: tuple[str, ...]
    preference_score: int

    @property
    def overspend_cents(self) -> int:
        """Return the subtotal above the target free-shipping threshold."""
        return self.subtotal_cents - self.threshold_cents


def read_preference_config(path: Path | None) -> PreferenceConfig:
    """Read one keyword per line plus optional ``@province`` directives."""
    if path is None or not path.exists():
        return PreferenceConfig(DEFAULT_PREFERENCE_KEYWORDS)

    keywords: list[str] = []
    province: str | None = None
    postal_code: str | None = None

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@"):
            directive, _, value = line.partition(" ")
            value = value.strip()
            if directive == "@province" and value:
                province = value
            elif directive == "@postal-code" and value:
                postal_code = value
            else:
                raise ValueError(f"Unknown or empty directive on {path}:{line_number}: {line}")
            continue
        keywords.append(line)

    normalized_keywords = tuple(dict.fromkeys(keyword.strip() for keyword in keywords if keyword.strip()))
    return PreferenceConfig(normalized_keywords or DEFAULT_PREFERENCE_KEYWORDS, province, postal_code)


def _match_text(value: str) -> str:
    """Normalize text for case-insensitive punctuation-tolerant matching."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^\w]+", " ", normalized)).strip()


def matched_keywords(coffee: Coffee, keywords: tuple[str, ...]) -> tuple[str, ...]:
    """Return distinct keywords found anywhere in useful coffee metadata."""
    fields = (
        coffee.name,
        coffee.origin,
        coffee.producer,
        coffee.process,
        coffee.varietal,
        coffee.altitude,
        coffee.roast_style,
        *(note.name for note in coffee.tasting_notes),
    )
    haystack = _match_text(" ".join(value for value in fields if value))
    matches = [keyword for keyword in keywords if _match_text(keyword) in haystack]
    return tuple(dict.fromkeys(matches))


def smallest_available_variant(coffee: Coffee) -> CoffeeVariant | None:
    """Return the lightest available variant with price and weight data."""
    usable = [
        variant
        for variant in coffee.variants
        if variant.availability
        and variant.price_cents is not None
        and variant.weight_grams is not None
        and variant.weight_grams > 0
        and is_retail_variant(variant.name)
    ]
    return min(usable, key=lambda variant: variant.weight_grams or 0) if usable else None


def cart_item_for_coffee(coffee: Coffee, keywords: tuple[str, ...]) -> CartItem | None:
    """Build an optimizer item from a coffee's smallest available variant."""
    variant = smallest_available_variant(coffee)
    matches = matched_keywords(coffee, keywords)
    if (
        variant is None
        or not matches
        or coffee.id is None
        or coffee.url is None
        or variant.price_cents is None
        or variant.weight_grams is None
    ):
        return None

    unit_price = price_per_100g_cents(variant.price_cents, variant.weight_grams)
    if unit_price is None:
        return None

    return CartItem(
        coffee_id=coffee.id,
        roaster_name=coffee.roaster.name,
        name=coffee.name,
        product_url=coffee.url,
        variant_id=variant.shopify_variant_id,
        variant_name=variant.name,
        bag_size=variant.bag_size or f"{variant.weight_grams}g",
        weight_grams=variant.weight_grams,
        price_cents=variant.price_cents,
        price_per_100g_cents=unit_price,
        matched_keywords=matches,
    )


def recommend_carts(
    items: list[CartItem],
    threshold_cents: int,
    *,
    max_bags: int = 6,
    limit: int = 3,
) -> list[CartCandidate]:
    """Rank distinct-coffee combinations that reach free shipping."""
    candidates: list[CartCandidate] = []
    maximum_size = min(max_bags, len(items))

    for size in range(1, maximum_size + 1):
        for combination in itertools.combinations(items, size):
            subtotal = sum(item.price_cents for item in combination)
            if subtotal < threshold_cents:
                continue

            keyword_union = tuple(dict.fromkeys(keyword for item in combination for keyword in item.matched_keywords))
            candidates.append(
                CartCandidate(
                    items=combination,
                    subtotal_cents=subtotal,
                    threshold_cents=threshold_cents,
                    matched_keywords=keyword_union,
                    preference_score=sum(len(item.matched_keywords) for item in combination),
                )
            )

    candidates.sort(
        key=lambda candidate: (
            candidate.overspend_cents,
            -len(candidate.matched_keywords),
            -candidate.preference_score,
            sum(item.price_per_100g_cents for item in candidate.items),
            tuple(item.coffee_id for item in candidate.items),
        )
    )
    return candidates[:limit]


def build_cart_permalink(candidate: CartCandidate, destination: Destination) -> str | None:
    """Build a Shopify cart permalink with an optional prefilled postal code."""
    if any(item.variant_id is None for item in candidate.items):
        return None

    hosts = {urlsplit(item.product_url).netloc for item in candidate.items}
    if len(hosts) != 1:
        return None

    lines = ",".join(f"{item.variant_id}:1" for item in candidate.items)
    parameters = {
        "storefront": "true",
        "checkout[shipping_address][country]": destination.country,
        "checkout[shipping_address][province]": destination.province,
    }
    if destination.postal_code:
        parameters["checkout[shipping_address][zip]"] = destination.postal_code

    return f"https://{hosts.pop()}/cart/{lines}?{urlencode(parameters)}"
