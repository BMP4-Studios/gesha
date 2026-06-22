"""Tests for cleanup rules shared across all roaster parser output."""

from gesha.normalization import NA_LABEL, normalize_search_text, normalize_tasting_notes, price_display


def test_price_display_handles_zero_cents() -> None:
    """Zero-valued prices are rendered as prices, not missing data."""
    assert price_display(0) == "$0.00"
    assert price_display(None) == NA_LABEL


def test_normalize_tasting_notes_from_string() -> None:
    """Delimited cup-note text becomes a stable list of note values."""
    # Cover the separators seen across current roaster fixtures.
    assert normalize_tasting_notes("berry; chocolate; floral") == ["berry", "chocolate", "floral"]
    assert normalize_tasting_notes("Maple, spice") == ["maple", "spice"]
    assert normalize_tasting_notes("Apricot • Honey • Orange") == ["apricot", "honey", "orange"]
    assert normalize_tasting_notes("Honey. Caramel. Chocolate.") == ["honey", "caramel", "chocolate"]


def test_normalize_search_text() -> None:
    """Searchable catalog labels are cleaned and lowercased."""
    # Decorative Unicode is removed, but meaningful punctuation like pipes remains.
    assert normalize_search_text("LOVEBUZZ 😵‍💫 💙") == "lovebuzz"
    assert normalize_search_text("‧₊˚❀༉‧₊˚. Bouquet. 𝒷𝓁𝑜𝓈𝓈𝑜𝓂𝑒𝒹 𝑒𝒹𝒾𝓉𝒾𝑜𝓃") == ". bouquet. blossomed edition"

    # Ordinary catalog fields are normalized without inventing taxonomy changes.
    assert normalize_search_text("Ethiopia") == "ethiopia"
    assert normalize_search_text("Colombia | Washed") == "colombia | washed"

    assert normalize_search_text("honey") == "honey"
    assert normalize_search_text("canada") == "canada"
    assert normalize_search_text("Ethiopia") == "ethiopia"
    assert normalize_search_text("CAUCA, COLOMBIA") == "cauca, colombia"

    # Missing values stay missing so display code can show the NONE label.
    assert normalize_search_text(None) is None
