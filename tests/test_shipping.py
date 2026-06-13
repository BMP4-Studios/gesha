"""Tests for Canadian destinations and shipping-threshold extraction."""

import pytest
from gesha.shipping import (
    SHIPPING_POLICIES,
    Destination,
    _detected_threshold_cents,
    resolve_destination,
)


def test_postal_code_infers_ontario_and_is_formatted() -> None:
    """A compact postal code supplies its province and normalized display."""
    destination = resolve_destination(postal_code="m5v3a8")

    assert destination == Destination(province="ON", postal_code="M5V 3A8")


def test_nunavut_postal_code_uses_its_specific_fsa_mapping() -> None:
    """The shared X prefix still distinguishes Nunavut from the territories."""
    destination = resolve_destination(postal_code="X0A 0H0")

    assert destination.province == "NU"


def test_conflicting_province_and_postal_code_are_rejected() -> None:
    """An inconsistent destination cannot silently choose the wrong threshold."""
    with pytest.raises(ValueError, match="belongs to ON, not QC"):
        resolve_destination(province="QC", postal_code="M5V 3A8")


def test_traffic_threshold_depends_on_destination() -> None:
    """Traffic's published policy distinguishes Ontario from the rest of Canada."""
    text = (
        "To qualify for free shipping in Quebec and Ontario, you'd have to spend 40$+ per order. "
        "For the rest of Canada, it's 50$+."
    )
    policy = SHIPPING_POLICIES["Traffic Coffee"]

    assert _detected_threshold_cents(policy, text, Destination(province="ON")) == 4000
    assert _detected_threshold_cents(policy, text, Destination(province="BC")) == 5000
