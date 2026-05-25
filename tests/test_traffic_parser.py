"""Tests for Traffic collection selectors and labeled product metadata."""

from gesha.parsers.traffic_parser import parse_traffic_collection, parse_traffic_product


def test_parse_traffic_collection() -> None:
    """Only canonical Traffic coffee collection links are accepted."""
    html = (
        '<a href="/collections/coffee/products/coffee-one">Coffee One</a>'
        '<a href="/collections/coffee/products/coffee-two?variant=123">Ignored Variant</a>'
        '<a href="/products/not-traffic">Ignored Product</a>'
        '<a href="/collections/coffee/products/coffee-one">Duplicate</a>'
    )

    urls = parse_traffic_collection(html, base_url="https://www.trafficcoffee.com")

    assert urls == ["https://www.trafficcoffee.com/collections/coffee/products/coffee-one"]


def test_parse_traffic_product() -> None:
    """A complete Traffic description maps into all main catalog fields."""
    html = (
        "<h1>La Piramide</h1>"
        '<span class="product-price">$24.00</span>'
        '<div class="product-block-description">'
        "Origin: Colombia "
        "Farmer: Luz Marina Trujillo "
        "Process: Washed "
        "Varietal: Caturra "
        "Altitude: 1900 masl "
        "Roast level: Filter "
        "Size: 250g "
        "In the cup: Orange, caramel; florals"
        "</div>"
    )

    coffee = parse_traffic_product(
        html,
        "https://www.trafficcoffee.com/collections/coffee/products/la-piramide",
    )

    assert coffee.roaster == "Traffic Coffee"
    assert coffee.name == "La Piramide"
    assert coffee.origin == "Colombia"
    assert coffee.producer == "Luz Marina Trujillo"
    assert coffee.process == "washed"
    assert coffee.varietal == "Caturra"
    assert coffee.altitude == "1900 masl"
    assert coffee.roast_style == "Filter"
    assert coffee.price_cents == 2400
    assert coffee.bag_size == "250g"
    assert coffee.tasting_notes == ["caramel", "floral", "orange"]


def test_parse_traffic_product_stops_notes_before_about_copy() -> None:
    """Narrative about-copy does not become tasting-note filter values."""
    html = (
        "<h1>Yellow Diamond</h1>"
        '<span class="product-price">$27.00</span>'
        '<div class="product-block-description">'
        "Origin: Kenya "
        "Process: Natural "
        "In the cup: apple cider, honey cake, flowers "
        "ABOUT Habil moved his family and this long story should not be notes."
        "</div>"
    )

    coffee = parse_traffic_product(
        html,
        "https://www.trafficcoffee.com/collections/coffee/products/yellow-diamond",
    )

    assert coffee.tasting_notes == ["apple cider", "flowers", "honey cake"]


def test_parse_traffic_product_extracts_size_from_variant_option() -> None:
    """Selected variant controls provide a missing Traffic bag size."""
    html = (
        "<h1>Collab avec Beton Arme 100g</h1>"
        '<span class="product-price">$10.00</span>'
        '<select name="id">'
        '<option selected="selected" value="123">100g</option>'
        "</select>"
        '<div class="product-block-description">'
        "Origin: Colombia "
        "Process: Washed "
        "In the cup: chocolate"
        "</div>"
    )

    coffee = parse_traffic_product(
        html,
        "https://www.trafficcoffee.com/collections/coffee/products/beton-arme-100g",
    )

    assert coffee.bag_size == "100g"
