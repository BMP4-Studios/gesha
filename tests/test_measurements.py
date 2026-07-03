"""Tests for bag-weight conversion and comparable unit pricing."""

from gesha.measurements import is_retail_variant, parse_weight_grams, price_per_100g_cents, weight_to_grams


def test_weight_conversion_supports_common_shopify_units() -> None:
    """Metric and imperial variant sizes normalize to rounded grams."""
    # Shopify stores may expose weights in any of these units.
    assert weight_to_grams(250, "g") == 250
    assert weight_to_grams(1, "kg") == 1000
    assert weight_to_grams(12, "oz") == 340
    assert weight_to_grams(2, "lb") == 907


def test_weight_parser_reads_free_form_variant_labels() -> None:
    """Variant text can supply weight when Shopify's weight fields are empty."""
    assert parse_weight_grams("Whole bean / 250 g") == 250
    assert parse_weight_grams("2lb bag") == 907
    assert parse_weight_grams("Default Title") is None


def test_price_per_100g_uses_integer_cents() -> None:
    """Unit prices remain stable and currency-safe for CLI comparison."""
    # Results are rounded cents because the CLI displays currency, not floats.
    assert price_per_100g_cents(2600, 300) == 867
    assert price_per_100g_cents(10000, 20) == 50000
    assert price_per_100g_cents(2500, 250) == 1000
    assert price_per_100g_cents(2500, None) is None


def test_retail_variant_filter_excludes_business_only_sizes() -> None:
    """Consumer recommendations do not choose Shopify wholesale variants."""
    assert is_retail_variant("250g")
    assert not is_retail_variant("5lb - B2B Only")
    assert not is_retail_variant("Wholesale case")
