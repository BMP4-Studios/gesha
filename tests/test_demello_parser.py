"""Tests for De Mello collection discovery and product-field extraction."""

from gesha.parsers.demello_parser import parse_demello_collection, parse_demello_product


def test_parse_demello_collection() -> None:
    """Collection parsing deduplicates accepted product page links."""
    html = (
        '<div data-url="/products/coffee-one"></div>'
        '<a href="/products/coffee-two">Coffee Two</a>'
        '<div data-url="/products/coffee-one"></div>'
    )

    urls = parse_demello_collection(html, base_url="https://hellodemello.com")

    assert urls == [
        "https://hellodemello.com/products/coffee-one",
        "https://hellodemello.com/products/coffee-two",
    ]


def test_parse_demello_product() -> None:
    """Detail blocks and description notes form a normalized coffee record."""
    html = (
        '<h1 class="product__title">Dancing Goats</h1>'
        '<span class="price-item price-item--regular">$16.00</span>'
        '<div class="product__description__content"><p>Milk Chocolate · Vanilla · Dark Cherry</p></div>'
        '<div class="metafield-rich_text_field">'
        '<p>Country : Brazil<br/>Region : Machado, Minas Gerais<br/>Producer : Group of Sitios<br/>Variety : Yellow Catuai<br/>Altitude : 1200 masl<br/>Process : Natural</p>'
        '</div>'
    )

    coffee = parse_demello_product(html, "https://hellodemello.com/products/dancing-goats")

    assert coffee.roaster == "De Mello Coffee"
    assert coffee.name == "Dancing Goats"
    assert coffee.origin == "Brazil"
    assert coffee.producer == "Group of Sitios"
    assert coffee.process == "natural"
    assert coffee.varietal == "Yellow Catuai"
    assert coffee.altitude == "1200 masl"
    assert coffee.price_cents == 1600
    assert "chocolate" in coffee.tasting_notes
    assert "dark cherry" in coffee.tasting_notes
    assert "vanilla" in coffee.tasting_notes


def test_parse_demello_product_extracts_size_from_variant_popout() -> None:
    """Variant theme markup supplies bag size when metadata does not."""
    html = (
        '<h1 class="product__title">Dancing Goats</h1>'
        '<span class="price-item price-item--regular">$16.00</span>'
        '<variant-selects>'
        '<small data-selected-value="">227g</small>'
        '<li selected="selected" value="227g">'
        '<a data-value="227g"><span>227g</span></a>'
        "</li>"
        "</variant-selects>"
        '<div class="product__description__content"><p>Milk Chocolate · Vanilla</p></div>'
        '<div class="metafield-rich_text_field">'
        '<p>Country : Brazil<br/>Process : Natural</p>'
        '</div>'
    )

    coffee = parse_demello_product(html, "https://hellodemello.com/products/dancing-goats")

    assert coffee.bag_size == "227g"
