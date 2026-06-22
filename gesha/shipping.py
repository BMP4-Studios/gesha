"""Destination handling and published free-shipping policy lookup."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

import requests
from bs4 import BeautifulSoup

CANADIAN_POSTAL_CODE = re.compile(r"^[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z]\s?\d[ABCEGHJ-NPRSTV-Z]\d$", re.IGNORECASE)
PROVINCE_BY_FIRST_LETTER: Final[dict[str, str]] = {
    # Canadian postal codes encode province/territory in the first letter.
    "A": "NL",
    "B": "NS",
    "C": "PE",
    "E": "NB",
    "G": "QC",
    "H": "QC",
    "J": "QC",
    "K": "ON",
    "L": "ON",
    "M": "ON",
    "N": "ON",
    "P": "ON",
    "R": "MB",
    "S": "SK",
    "T": "AB",
    "V": "BC",
    "X": "NT",
    "Y": "YT",
}
CANADIAN_PROVINCES: Final[set[str]] = {
    # Accepted Canada Post province and territory abbreviations.
    "AB",
    "BC",
    "MB",
    "NB",
    "NL",
    "NS",
    "NT",
    "NU",
    "ON",
    "PE",
    "QC",
    "SK",
    "YT",
}


@dataclass(frozen=True)
class Destination:
    """Canadian shipping destination used for policy selection and checkout."""

    province: str = "ON"
    postal_code: str | None = None
    country: str = "Canada"


@dataclass(frozen=True)
class ShippingPolicy:
    """Known shipping thresholds and a public page used to refresh them."""

    roaster_name: str
    policy_url: str
    fallback_cents: dict[str, int]
    detection_patterns: dict[str, tuple[str, ...]]

    def threshold_for(self, province: str) -> int | None:
        """Return a province-specific threshold before the Canada fallback."""
        return self.fallback_cents.get(province, self.fallback_cents.get("CA"))

    def patterns_for(self, province: str) -> tuple[str, ...] | None:
        """Return province-specific detection patterns before the fallback."""
        return self.detection_patterns.get(province, self.detection_patterns.get("CA"))


@dataclass(frozen=True)
class ShippingThreshold:
    """Resolved threshold with enough provenance for honest CLI output."""

    amount_cents: int
    policy_url: str
    detected_live: bool


TODO_SHIPPING_FALLBACK_CENTS: Final[int] = 5000
TODO_SHIPPING_DETECTION_PATTERNS: Final[tuple[str, ...]] = (
    r"free shipping.*?\$?(\d+(?:\.\d{1,2})?)",
    r"orders?\s+(?:above|over)\s+\$?(\d+(?:\.\d{1,2})?)",
)


def _todo_shipping_policy(roaster_name: str, policy_url: str) -> ShippingPolicy:
    """Create an explicitly temporary shipping policy for newly batched roasters."""
    # TODO: Replace this $50 fallback with each roaster's verified threshold and
    # policy-page regex before treating the policy data as final.
    return ShippingPolicy(
        roaster_name=roaster_name,
        policy_url=policy_url,
        fallback_cents={"CA": TODO_SHIPPING_FALLBACK_CENTS},
        detection_patterns={"CA": TODO_SHIPPING_DETECTION_PATTERNS},
    )


SHIPPING_POLICIES: Final[dict[str, ShippingPolicy]] = {
    # These are known fallbacks plus regexes for refreshing against public
    # policy pages. Fallbacks keep cart optimization useful when pages change.
    "De Mello Coffee": ShippingPolicy(
        roaster_name="De Mello Coffee",
        policy_url="https://hellodemello.com/pages/faq",
        fallback_cents={"CA": 4500},
        detection_patterns={"CA": (r"orders\s+(?:above|over)\s+\$?(\d+(?:\.\d{1,2})?)",)},
    ),
    "Traffic Coffee": ShippingPolicy(
        roaster_name="Traffic Coffee",
        policy_url="https://www.trafficcoffee.com/pages/faq",
        fallback_cents={"ON": 4000, "QC": 4000, "CA": 5000},
        detection_patterns={
            "ON": (r"free shipping in quebec and ontario.*?spend\s+(\d+(?:\.\d{1,2})?)\$",),
            "QC": (r"free shipping in quebec and ontario.*?spend\s+(\d+(?:\.\d{1,2})?)\$",),
            "CA": (r"rest of canada.*?(\d+(?:\.\d{1,2})?)\$\+",),
        },
    ),
    "Porte Bleue": ShippingPolicy(
        roaster_name="Porte Bleue",
        policy_url="https://portebleue.ca/",
        fallback_cents={"CA": 10000},
        detection_patterns={"CA": (r"free shipping within canada.*?orders\s+(?:above|over)\s+\$?(\d+(?:\.\d{1,2})?)",)},
    ),
    "Colorfull Coffee": ShippingPolicy(
        roaster_name="Colorfull Coffee",
        policy_url="https://colorfullcoffee.com/",
        fallback_cents={"CA": 10000},
        detection_patterns={"CA": (r"free shipping.*?\$?(\d+(?:\.\d{1,2})?)\s*\+",)},
    ),
    "The Angry Roaster": ShippingPolicy(
        roaster_name="The Angry Roaster",
        policy_url="https://theangryroaster.com/",
        fallback_cents={"CA": 6500},
        detection_patterns={"CA": (r"free shipping\s+(?:for\s+)?orders\s+(?:above|over)\s+\$?(\d+(?:\.\d{1,2})?)",)},
    ),
    "House of Funk": _todo_shipping_policy("House of Funk", "https://www.houseoffunkbrewing.com/"),
    "Rogue Wave Coffee": _todo_shipping_policy("Rogue Wave Coffee", "https://roguewavecoffee.ca/"),
    "Quietly Coffee": _todo_shipping_policy("Quietly Coffee", "https://www.quietlycoffee.com/"),
    "Escape Coffee Roasters": _todo_shipping_policy("Escape Coffee Roasters", "https://escape.cafe/"),
    "Pirates of Coffee": _todo_shipping_policy("Pirates of Coffee", "https://piratesofcoffee.com/"),
    "94 Celcius": _todo_shipping_policy("94 Celcius", "https://94celcius.com/en"),
    "Cafe Pista": _todo_shipping_policy("Cafe Pista", "https://cafepista.com/en"),
    "Jungle Livraison Cafe": _todo_shipping_policy(
        "Jungle Livraison Cafe",
        "https://junglelivraisoncafe.com/collections/les-melanges",
    ),
    "Ambros Coffee": _todo_shipping_policy("Ambros Coffee", "https://ambroscoffee.com/"),
    "Za & Klo": _todo_shipping_policy("Za & Klo", "https://zaandklo.com/"),
    "Nektar Cafeologue": _todo_shipping_policy("Nektar Cafeologue", "https://nektar.ca/en"),
    "September Coffee": _todo_shipping_policy("September Coffee", "https://september.coffee/"),
    "Kohi": _todo_shipping_policy("Kohi", "https://kohi.ca/en/collections/frontpage"),
    "Subtext Coffee": _todo_shipping_policy("Subtext Coffee", "https://www.subtext.coffee/"),
    "Nucleus Coffee": _todo_shipping_policy("Nucleus Coffee", "https://nucleuscoffee.com/"),
    "The Artery Community Roasters": _todo_shipping_policy(
        "The Artery Community Roasters",
        "https://thearterycommunityroasters.com/",
    ),
    "Sips Truck Coffee Roasters": _todo_shipping_policy("Sips Truck Coffee Roasters", "https://sipstruck.com/"),
    "Monogram Coffee": _todo_shipping_policy("Monogram Coffee", "https://monogramcoffee.com/"),
    "Ethica Coffee Roasters": _todo_shipping_policy("Ethica Coffee Roasters", "https://ethicaroasters.com/"),
    "Rabbit Hole Roasters": _todo_shipping_policy(
        "Rabbit Hole Roasters",
        "https://www.rabbitholeroasters.com/",
    ),
    "Narval": _todo_shipping_policy("Narval", "https://narval.cafe/en"),
}


def normalize_postal_code(value: str) -> str:
    """Validate and format a Canadian postal code as ``A1A 1A1``."""
    # Remove user-entered spacing before validating against the Canada Post form.
    compact = re.sub(r"\s+", "", value).upper()
    if CANADIAN_POSTAL_CODE.fullmatch(compact) is None:
        raise ValueError(f"'{value}' is not a valid Canadian postal code.")

    # Store and display postal codes with the standard middle space.
    return f"{compact[:3]} {compact[3:]}"


def province_for_postal_code(postal_code: str) -> str:
    """Infer the province or territory represented by a postal-code FSA."""
    normalized = normalize_postal_code(postal_code)

    # ``X`` covers three northern territories; these FSAs are Nunavut-specific.
    if normalized[:3] in {"X0A", "X0B", "X0C"}:
        return "NU"
    return PROVINCE_BY_FIRST_LETTER[normalized[0]]


def resolve_destination(province: str | None = None, postal_code: str | None = None) -> Destination:
    """Resolve explicit and inferred destination values, defaulting to Ontario."""
    # A postal code is optional, but when present it can infer province and
    # prefill Shopify checkout links.
    normalized_postal = normalize_postal_code(postal_code) if postal_code else None
    inferred_province = province_for_postal_code(normalized_postal) if normalized_postal else None
    normalized_province = province.upper() if province else None

    # Validate explicit province values before using them in policy lookups.
    if normalized_province and normalized_province not in CANADIAN_PROVINCES:
        raise ValueError(f"'{province}' is not a valid Canadian province or territory abbreviation.")

    # Do not silently accept contradictory destination inputs.
    if normalized_province and inferred_province and normalized_province != inferred_province:
        raise ValueError(f"Postal code {normalized_postal} belongs to {inferred_province}, not {normalized_province}.")

    # Ontario is the project default when the user gives no destination at all.
    return Destination(province=normalized_province or inferred_province or "ON", postal_code=normalized_postal)


def _detected_threshold_cents(policy: ShippingPolicy, text: str, destination: Destination) -> int | None:
    """Extract a destination-appropriate dollar amount from policy-page text."""
    # Some roasters publish province-specific thresholds; fall back to national
    # patterns when no province-specific pattern exists.
    patterns = policy.patterns_for(destination.province)
    if patterns is None:
        return None

    # Flatten page text before regex matching so HTML line breaks do not matter.
    normalized_text = re.sub(r"\s+", " ", text).lower()
    for pattern in patterns:
        match = re.search(pattern, normalized_text, flags=re.IGNORECASE)
        if match:
            # Regexes capture dollar values; the rest of the app stores cents.
            return round(float(match.group(1)) * 100)
    return None


def resolve_shipping_threshold(
    roaster_name: str,
    destination: Destination,
    *,
    refresh: bool = True,
    timeout: float = 8,
) -> ShippingThreshold | None:
    """Refresh a published threshold when possible, then use the known fallback."""
    # Unknown roasters simply cannot produce free-shipping recommendations.
    policy = SHIPPING_POLICIES.get(roaster_name)
    if policy is None:
        return None

    if refresh:
        try:
            # Policy pages are ordinary web pages, not Shopify APIs.
            response = requests.get(
                policy.policy_url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; Gesha cart optimizer)"},
                timeout=timeout,
            )
            response.raise_for_status()

            # BeautifulSoup removes markup so regexes operate on human-visible text.
            text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
            detected = _detected_threshold_cents(policy, text, destination)
            if detected is not None:
                return ShippingThreshold(detected, policy.policy_url, detected_live=True)
        except requests.RequestException:
            # Network failures should not prevent cart recommendations when a
            # configured fallback is available.
            pass

    # Fallbacks are marked as not live so the CLI can be honest about provenance.
    fallback = policy.threshold_for(destination.province)
    if fallback is None:
        return None
    return ShippingThreshold(fallback, policy.policy_url, detected_live=False)
