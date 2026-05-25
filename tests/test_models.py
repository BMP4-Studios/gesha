"""Tests for validation performed at the scraper-to-service data boundary."""

from gesha.models.coffee import CoffeeData


def test_coffee_data_model_strips_values() -> None:
    """Identity text is trimmed before the service attempts record matching."""
    coffee = CoffeeData(roaster="  Hatch Coffee  ", name="  Guatemala  ")
    assert coffee.roaster == "Hatch Coffee"
    assert coffee.name == "Guatemala"


def test_coffee_data_model_normalizes_notes() -> None:
    """Tasting notes are lowercased and stripped for consistent filtering."""
    coffee = CoffeeData(roaster="Hatch Coffee", name="Test", tasting_notes=[" Berry ", "chocolate"])
    assert coffee.tasting_notes == ["berry", "chocolate"]
