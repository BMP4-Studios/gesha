"""Tests for cleanup rules shared across all roaster parser output."""

from gesha.normalization import normalize_tasting_notes, remove_emojis


def test_normalize_tasting_notes_from_string() -> None:
    """Delimited cup-note text becomes a stable list of note values."""
    assert normalize_tasting_notes("berry; chocolate; floral") == ["berry", "chocolate", "floral"]
    assert normalize_tasting_notes("Maple, spice") == ["maple", "spice"]


def test_remove_emojis() -> None:
    """Decorative storefront typography does not leak into catalog fields."""
    assert remove_emojis("LOVEBUZZ 😵‍💫 💙") == "lovebuzz"
    assert remove_emojis("‧₊˚❀༉‧₊˚. Bouquet. 𝒷𝓁𝑜𝓈𝓈𝑜𝓂𝑒𝒹 𝑒𝒹𝒾𝓉𝒾𝑜𝓃") == ". bouquet. blossomed edition"

    assert remove_emojis("honey") == "honey"
    assert remove_emojis("canada") == "canada"
    assert remove_emojis("Ethiopia") == "ethiopia"
    assert remove_emojis("CAUCA, COLOMBIA") == "cauca, colombia"

    assert normalize_tasting_notes("Apricot • Honey • Orange") == ["apricot", "honey", "orange"]
    assert normalize_tasting_notes("Honey. Caramel. Chocolate.") == ["honey", "caramel", "chocolate"]
