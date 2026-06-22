"""Tests for preference parsing and deterministic cart recommendations."""

from pathlib import Path

from gesha.cart import (
    CartItem,
    build_cart_permalink,
    cart_item_for_coffee,
    read_preference_config,
    recommend_carts,
)
from gesha.db.models import Coffee, CoffeeVariant, Roaster, TastingNote
from gesha.shipping import Destination


def test_preference_file_supports_destination_directives(tmp_path: Path) -> None:
    """Keywords remain one-per-line while destination settings stay explicit."""
    path = tmp_path / "preferences.txt"

    # Mix comments, directives, duplicate includes, and exclusions to exercise
    # the same file shape a user would maintain by hand.
    path.write_text(
        "# My coffee profile\n@province QC\n@postal-code H2X 1Y4\nnatural\npeach\nnatural\n!decaf\n! dark roast\n",
        encoding="utf-8",
    )

    config = read_preference_config(path)

    assert config.province == "QC"
    assert config.postal_code == "H2X 1Y4"
    assert config.keywords == ("natural", "peach")
    assert config.excluded_keywords == ("decaf", "dark roast")


def test_cart_item_uses_smallest_variant_and_matches_all_metadata() -> None:
    """A producer or tasting-note match can qualify the lightest bag."""
    # Build a real ORM-shaped coffee because cart item creation reads
    # relationships, variants, and tasting-note rows.
    coffee = Coffee(
        id=7,
        name="Las Flores",
        producer="Wilton Benitez",
        process="Washed",
        url="https://example.test/products/las-flores",
        roaster=Roaster(name="Test Roaster"),
        tasting_notes=[TastingNote(name="peach"), TastingNote(name="jasmine")],
        variants=[
            CoffeeVariant(
                shopify_variant_id="large",
                name="1kg",
                price_cents=7000,
                bag_size="1kg",
                weight_grams=1000,
                availability=True,
            ),
            CoffeeVariant(
                shopify_variant_id="small",
                name="250g",
                price_cents=2500,
                bag_size="250g",
                weight_grams=250,
                availability=True,
            ),
        ],
    )

    item = cart_item_for_coffee(coffee, ("wilton benitez", "peach", "natural"))

    assert item is not None
    assert item.variant_id == "small"
    assert item.bag_size == "250g"
    assert item.origin is None
    assert item.process == "Washed"
    assert item.tasting_notes == ("peach", "jasmine")
    assert item.price_per_100g_cents == 1000
    assert item.matched_keywords == ("wilton benitez", "peach")


def test_cart_item_skips_bags_larger_than_one_pound() -> None:
    """Sold-out small bags do not promote an expensive 2lb cart item."""
    coffee = Coffee(
        id=9,
        name="Traffic Fruit Bomb",
        process="Natural",
        url="https://example.test/products/fruit-bomb",
        roaster=Roaster(name="Test Roaster"),
        tasting_notes=[TastingNote(name="mango")],
        variants=[
            CoffeeVariant(
                shopify_variant_id="sold-out-small",
                name="250g",
                price_cents=2500,
                bag_size="250g",
                weight_grams=250,
                availability=False,
            ),
            CoffeeVariant(
                shopify_variant_id="one-pound",
                name="1lb",
                price_cents=4200,
                bag_size="1lb",
                weight_grams=454,
                availability=True,
            ),
            CoffeeVariant(
                shopify_variant_id="two-pound",
                name="2lb",
                price_cents=7800,
                bag_size="2lb",
                weight_grams=907,
                availability=True,
            ),
        ],
    )

    item = cart_item_for_coffee(coffee, ("natural", "mango"))

    assert item is not None
    assert item.variant_id == "one-pound"
    assert item.bag_size == "1lb"


def test_cart_item_excludes_coffee_when_only_large_bags_are_available() -> None:
    """A coffee is omitted if every purchasable variant is larger than 1lb."""
    coffee = Coffee(
        id=10,
        name="Traffic Fruit Barrel",
        process="Natural",
        url="https://example.test/products/fruit-barrel",
        roaster=Roaster(name="Test Roaster"),
        tasting_notes=[TastingNote(name="mango")],
        variants=[
            CoffeeVariant(
                shopify_variant_id="two-pound",
                name="2lb",
                price_cents=7800,
                bag_size="2lb",
                weight_grams=907,
                availability=True,
            ),
        ],
    )

    item = cart_item_for_coffee(coffee, ("natural", "mango"))

    assert item is None


def test_cart_item_excludes_coffees_matching_negative_keywords() -> None:
    """A negative match removes a coffee even when it also matches preferences."""
    coffee = Coffee(
        id=8,
        name="Colombia Natural Decaf",
        process="Natural",
        url="https://example.test/products/decaf",
        roaster=Roaster(name="Test Roaster"),
        tasting_notes=[TastingNote(name="peach")],
        variants=[
            CoffeeVariant(
                shopify_variant_id="small",
                name="250g",
                price_cents=2200,
                bag_size="250g",
                weight_grams=250,
                availability=True,
            ),
        ],
    )

    item = cart_item_for_coffee(coffee, ("natural", "peach"), ("decaf",))

    assert item is None


def test_recommendations_include_all_matching_items_even_below_threshold() -> None:
    """The single cart keeps every eligible coffee instead of searching combinations."""
    items = [
        _item(1, 2600, 867, ("natural", "berry")),
        _item(2, 2300, 767, ("peach",)),
        _item(3, 3000, 1000, ("natural", "mango")),
    ]

    candidates = recommend_carts(items, 10000)

    assert len(candidates) == 1
    assert [item.coffee_id for item in candidates[0].items] == [1, 3, 2]
    assert candidates[0].subtotal_cents == 7900
    assert candidates[0].overspend_cents == -2100


def test_recommendations_prioritize_included_keyword_order_in_one_cart() -> None:
    """A higher-list keyword sorts rows above lower-only matches."""
    # ``natural`` is first in the preference list, so it appears above coffees
    # that match only later preferences.
    items = [
        _item(1, 4500, 900, ("floral", "funky")),
        _item(2, 4600, 920, ("natural",)),
    ]

    candidates = recommend_carts(
        items,
        4000,
        keyword_priority=("natural", "floral", "funky"),
    )

    assert [item.coffee_id for item in candidates[0].items] == [2, 1]
    assert candidates[0].matched_keywords == ("natural", "floral", "funky")
    assert candidates[0].overspend_cents == 5100


def test_recommendation_items_are_ordered_by_preference_fit() -> None:
    """Rows inside the chosen cart put stronger keyword matches first."""
    items = [
        _item(1, 2400, 800, ("funky",)),
        _item(2, 2400, 800, ("natural",)),
        _item(3, 2400, 800, ("natural", "floral")),
    ]

    candidate = recommend_carts(
        items,
        7000,
        keyword_priority=("natural", "floral", "funky"),
    )[0]

    assert [item.coffee_id for item in candidate.items] == [3, 2, 1]


def test_recommendations_return_no_cart_when_no_items_match() -> None:
    """No eligible coffees means no cart recommendation."""
    assert recommend_carts([], 4500) == []


def test_cart_permalink_prefills_canadian_checkout_destination() -> None:
    """Shopify variant IDs and a postal code produce a usable cart URL."""
    # Use a one-item candidate so the expected permalink is easy to inspect.
    candidate = recommend_carts([_item(1, 5000, 1000, ("natural",))], 4500)[0]

    url = build_cart_permalink(candidate, Destination(province="ON", postal_code="M5V 3A8"))

    assert url is not None
    assert "example.test/cart/variant-1%3A1" not in url
    assert "example.test/cart/variant-1:1" in url
    assert "checkout%5Bshipping_address%5D%5Bprovince%5D=ON" in url
    assert "checkout%5Bshipping_address%5D%5Bzip%5D=M5V+3A8" in url


def _item(
    coffee_id: int,
    price_cents: int,
    unit_price_cents: int,
    keywords: tuple[str, ...],
) -> CartItem:
    """Create a compact optimizer item for combination tests."""
    # Tests that focus on ranking do not need full ORM objects.
    return CartItem(
        coffee_id=coffee_id,
        roaster_name="Test Roaster",
        name=f"Coffee {coffee_id}",
        origin=None,
        process=None,
        tasting_notes=(),
        product_url=f"https://example.test/products/{coffee_id}",
        variant_id=f"variant-{coffee_id}",
        variant_name="250g",
        bag_size="250g",
        weight_grams=250,
        price_cents=price_cents,
        price_per_100g_cents=unit_price_cents,
        matched_keywords=keywords,
    )
