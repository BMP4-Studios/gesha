"""Explainable keyword matching and free-shipping cart optimization."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from gesha.db.models import Coffee, CoffeeVariant
from gesha.measurements import is_retail_variant, price_per_100g_cents
from gesha.shipping import Destination

DEFAULT_PREFERENCE_KEYWORDS = (
    # These defaults make ``gesha cart`` useful before a preference file exists.
    # They describe the fruity/funky/natural lane this project is currently
    # optimizing for.
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
MAX_CART_BAG_WEIGHT_GRAMS = 500


@dataclass(frozen=True)
class PreferenceConfig:
    """Included/excluded keywords and optional destination directives."""

    keywords: tuple[str, ...]
    excluded_keywords: tuple[str, ...] = ()
    province: str | None = None
    postal_code: str | None = None


@dataclass(frozen=True)
class CartItem:
    """One smallest-bag coffee variant eligible for optimization."""

    coffee_id: int
    roaster_name: str
    name: str
    origin: str | None
    process: str | None
    tasting_notes: tuple[str, ...]
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
    """One ranked cart containing distinct coffees from one roaster."""

    items: tuple[CartItem, ...]
    subtotal_cents: int
    threshold_cents: int
    matched_keywords: tuple[str, ...]
    preference_score: int
    priority_coverage: tuple[int, ...] = ()

    @property
    def overspend_cents(self) -> int:
        """Return the subtotal relative to the target free-shipping threshold."""
        return self.subtotal_cents - self.threshold_cents


def read_preference_config(path: Path | None) -> PreferenceConfig:
    """Read include/exclude keywords plus optional ``@province`` directives."""
    # A missing preferences file is not an error: the CLI should still produce
    # recommendations from the built-in fruity/funky defaults.
    if path is None or not path.exists():
        return PreferenceConfig(keywords=DEFAULT_PREFERENCE_KEYWORDS)

    # Parse the file into three independent concerns: positive keyword matches,
    # negative keyword exclusions, and optional shipping destination hints.
    keywords: list[str] = []
    excluded_keywords: list[str] = []
    province: str | None = None
    postal_code: str | None = None

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()

        # Blank lines and comments let the user group preference files freely.
        if not line or line.startswith("#"):
            continue

        # ``@`` lines are configuration directives rather than coffee keywords.
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

        # ``!`` lines are hard exclusions: any matching coffee is removed before
        # cart combinations are considered.
        if line.startswith("!"):
            excluded_keyword = line[1:].strip()
            if not excluded_keyword:
                raise ValueError(f"Empty excluded keyword on {path}:{line_number}.")
            excluded_keywords.append(excluded_keyword)
            continue

        # Any other non-empty line is an include keyword, kept in user order so
        # earlier entries can become higher-priority ranking signals.
        keywords.append(line)

    # ``dict.fromkeys`` is an order-preserving de-dupe. Keeping the first copy
    # matters because keyword order is used later as a preference priority list.
    normalized_keywords = tuple(dict.fromkeys(keyword.strip() for keyword in keywords if keyword.strip()))
    normalized_excluded_keywords = tuple(
        dict.fromkeys(keyword.strip() for keyword in excluded_keywords if keyword.strip())
    )
    return PreferenceConfig(
        keywords=normalized_keywords or DEFAULT_PREFERENCE_KEYWORDS,
        excluded_keywords=normalized_excluded_keywords,
        province=province,
        postal_code=postal_code,
    )


def _match_text(value: str) -> str:
    """Normalize text for case-insensitive punctuation-tolerant matching."""
    # Unicode normalization makes visually similar characters compare the same.
    normalized = unicodedata.normalize("NFKC", value).casefold()

    # Replace punctuation with spaces so "co-ferment" can match text that uses
    # slightly different separators.
    return re.sub(r"\s+", " ", re.sub(r"[^\w]+", " ", normalized)).strip()


def matched_keywords(coffee: Coffee, keywords: tuple[str, ...]) -> tuple[str, ...]:
    """Return distinct keywords found anywhere in useful coffee metadata."""
    # Treat all searchable metadata as one haystack so preference terms can
    # match origin, process, producer, varietal, altitude, roast style, or notes.
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

    # Iterate over the user's keyword order so matches preserve priority.
    matches = [keyword for keyword in keywords if _match_text(keyword) in haystack]
    return tuple(dict.fromkeys(matches))


def smallest_available_variant(coffee: Coffee) -> CoffeeVariant | None:
    """Return the lightest available variant with price and weight data."""
    # Cart links and unit prices need a real purchasable variant. Wholesale/B2B
    # variants and bags above roughly 1 lb are filtered out because they are not
    # normal consumer bags for these recommendations.
    usable = [
        variant
        for variant in coffee.variants
        if variant.availability
        and variant.price_cents is not None
        and variant.weight_grams is not None
        and variant.weight_grams > 0
        and variant.weight_grams <= MAX_CART_BAG_WEIGHT_GRAMS
        and is_retail_variant(variant.name)
    ]

    # Smaller bags make mixed carts easier and are the default shopping behavior
    # requested for the optimizer.
    return min(usable, key=lambda variant: variant.weight_grams or 0) if usable else None


def cart_item_for_coffee(
    coffee: Coffee,
    keywords: tuple[str, ...],
    excluded_keywords: tuple[str, ...] = (),
) -> CartItem | None:
    """Build an optimizer item from a coffee's smallest available variant."""
    # Exclusions are checked before includes so a disliked process/producer can remove a coffee even when it also matches a positive keyword.
    if matched_keywords(coffee, excluded_keywords):
        return None

    # The optimizer only considers coffees that both match preferences and have
    # enough variant data to build a Shopify cart permalink.
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

    # Copy ORM fields into an immutable data object so combination scoring does
    # not depend on an open SQLAlchemy session.
    return CartItem(
        coffee_id=coffee.id,
        roaster_name=coffee.roaster.name,
        name=coffee.name,
        origin=coffee.origin,
        process=coffee.process,
        tasting_notes=tuple(note.name for note in coffee.tasting_notes),
        product_url=coffee.url,
        variant_id=variant.shopify_variant_id,
        variant_name=variant.name,
        bag_size=variant.bag_size or f"{variant.weight_grams}g",
        weight_grams=variant.weight_grams,
        price_cents=variant.price_cents,
        price_per_100g_cents=unit_price,
        matched_keywords=matches,
    )


def _ordered_keyword_union(combination: tuple[CartItem, ...], keyword_priority: tuple[str, ...]) -> tuple[str, ...]:
    """Return matched keywords in preference-list order, retaining any extras."""
    # First collect matches in cart-row order, then optionally reorder known
    # preference keywords according to the user file.
    matched_in_item_order = tuple(dict.fromkeys(keyword for item in combination for keyword in item.matched_keywords))
    if not keyword_priority:
        return matched_in_item_order

    # Unknown extra matches remain after prioritized keywords so nothing is lost
    # when future matching rules introduce terms outside the preference file.
    matched = set(matched_in_item_order)
    priority_set = set(keyword_priority)
    prioritized = tuple(keyword for keyword in keyword_priority if keyword in matched)
    extras = tuple(keyword for keyword in matched_in_item_order if keyword not in priority_set)
    return prioritized + extras


def _priority_coverage(matched_keywords: tuple[str, ...], keyword_priority: tuple[str, ...]) -> tuple[int, ...]:
    """Build a lexicographic coverage vector for ordered preference keywords."""
    # A tuple like (1, 0, 1) lets normal tuple sorting prefer carts that cover
    # earlier keywords first, not just carts with the most total keywords.
    matched = set(matched_keywords)
    return tuple(1 if keyword in matched else 0 for keyword in keyword_priority)


def _cart_item_sort_key(item: CartItem, keyword_priority: tuple[str, ...]) -> tuple[tuple[int, ...], int, int, int]:
    """Order cart rows from strongest preference fit to weakest."""
    priority_coverage = _priority_coverage(item.matched_keywords, keyword_priority)

    # Negative values turn Python's ascending sort into "more matches first";
    # unit price and ID make the remaining order deterministic.
    return (
        tuple(-covered for covered in priority_coverage),
        -len(item.matched_keywords),
        item.price_per_100g_cents,
        item.coffee_id,
    )


def recommend_carts(
    items: list[CartItem],
    threshold_cents: int,
    *,
    keyword_priority: tuple[str, ...] | None = None,
) -> list[CartCandidate]:
    """Build one cart containing every item that already matched preferences.

    Args:
        items: Candidate coffees that already matched the user's include
            keywords, avoided excluded keywords, and have enough variant data to
            be placed in a Shopify cart.
        threshold_cents: Free-shipping target in integer cents. The returned
            cart records this value for display, but coffees are not removed
            when the subtotal is below the threshold.
        keyword_priority: Optional ordered preference list used to rank carts
            and rows. Earlier keywords are treated as more important than later
            keywords.

    Returns:
        A single cart containing all supplied items, or an empty list when no
        items were supplied.
    """
    priority_keywords = keyword_priority or ()
    if not items:
        return []

    # Display the full cart from strongest preference fit to weakest.
    ordered_items = tuple(sorted(items, key=lambda item: _cart_item_sort_key(item, priority_keywords)))
    keyword_union = _ordered_keyword_union(ordered_items, priority_keywords)

    # The function still returns a list so the CLI shape remains compatible with
    # older callers, but there is now at most one cart per roaster.
    return [
        CartCandidate(
            items=ordered_items,
            subtotal_cents=sum(item.price_cents for item in ordered_items),
            threshold_cents=threshold_cents,
            matched_keywords=keyword_union,
            preference_score=sum(len(item.matched_keywords) for item in ordered_items),
            priority_coverage=_priority_coverage(keyword_union, priority_keywords),
        )
    ]


def build_cart_permalink(candidate: CartCandidate, destination: Destination) -> str | None:
    """Build a Shopify cart permalink with an optional prefilled postal code."""
    # Shopify cart permalinks require variant IDs, not product URLs.
    if any(item.variant_id is None for item in candidate.items):
        return None

    # A single cart can only belong to one Shopify storefront.
    hosts = {urlsplit(item.product_url).netloc for item in candidate.items}
    if len(hosts) != 1:
        return None

    # ``variant_id:quantity`` is Shopify's public cart permalink format.
    lines = ",".join(f"{item.variant_id}:1" for item in candidate.items)
    parameters = {
        "storefront": "true",
        "checkout[shipping_address][country]": destination.country,
        "checkout[shipping_address][province]": destination.province,
    }
    if destination.postal_code:
        # Shopify checkout recognizes this nested parameter and can prefill it.
        parameters["checkout[shipping_address][zip]"] = destination.postal_code

    return f"https://{hosts.pop()}/cart/{lines}?{urlencode(parameters)}"
