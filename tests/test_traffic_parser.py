from gesha.parsers.traffic_parser import parse_traffic_collection, parse_traffic_product


def test_parse_traffic_collection() -> None:
    html = (
        '<a href="/collections/coffee/products/coffee-one">Coffee One</a>'
        '<a href="/collections/coffee/products/coffee-two?variant=123">Ignored Variant</a>'
        '<a href="/products/not-traffic">Ignored Product</a>'
        '<a href="/collections/coffee/products/coffee-one">Duplicate</a>'
    )

    urls = parse_traffic_collection(html, base_url="https://www.trafficcoffee.com")

    assert urls == ["https://www.trafficcoffee.com/collections/coffee/products/coffee-one"]


def test_parse_traffic_product() -> None:
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
