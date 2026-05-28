"""Tests for behavior shared by JSON-backed Shopify scraper adapters."""

from bs4 import BeautifulSoup

from gesha.scrapers.shopify_scraper import AngryRoasterScraper, ColorfullScraper, DeMelloScraper, PorteBleueScraper, TrafficScraper


def test_shopify_collection_extracts_canonical_product_urls() -> None:
    """Collection-prefixed links collapse to one stable product URL form."""
    html = (
        '<a href="/collections/coffee/products/gold-92">Gold 92</a>'
        '<a href="/products/las-flores?variant=123">Las Flores</a>'
        '<a href="/collections/merch">Merch</a>'
    )

    urls = PorteBleueScraper().extract_product_urls(html)

    assert urls == [
        "https://portebleue.ca/products/gold-92",
        "https://portebleue.ca/products/las-flores",
    ]


def test_shopify_collection_extracts_data_urls_and_filters_handles() -> None:
    """Collection parsing supports theme data attributes and roaster exclusions."""
    html = (
        '<div data-url="/products/coffee-one"></div>'
        '<a href="/products/coffee-two">Coffee Two</a>'
        '<a href="/products/starter-kit">Starter Kit</a>'
        '<div data-url="/products/coffee-one"></div>'
    )

    urls = DeMelloScraper().extract_product_urls(html)

    assert urls == [
        "https://hellodemello.com/products/coffee-one",
        "https://hellodemello.com/products/coffee-two",
    ]


def test_shopify_product_json_parses_labeled_specs() -> None:
    """Structured Shopify descriptions populate normalized catalog fields."""
    product = {
        "title": "Colombia - Gesha - Inza",
        "price": 2300,
        "available": True,
        "type": "Coffee",
        "tags": ["coffee", "washed"],
        "description": (
            "<p>Specs</p>"
            "<p>Region: CAUCA, COLOMBIA</p>"
            "<p>Variety: GESHA</p>"
            "<p>Method: WASHED</p>"
            "<p>Altitude: 1900 MASL</p>"
            "<p>Coffee Producers: RAFAEL VELASQUEZ</p>"
            "<p>Notes: BERGAMOT, CLEMENTINE, LAVENDER & BLUEBERRIES</p>"
            "<p>Amount: 250g</p>"
        ),
    }

    coffee = AngryRoasterScraper()._coffee_from_product(
        product,
        "https://theangryroaster.com/products/colombia-gesha-inza",
    )

    assert coffee.roaster == "The Angry Roaster"
    assert coffee.name == "Colombia - Gesha - Inza"
    assert coffee.origin == "CAUCA, COLOMBIA"
    assert coffee.producer == "RAFAEL VELASQUEZ"
    assert coffee.process == "washed"
    assert coffee.varietal == "GESHA"
    assert coffee.altitude == "1900 MASL"
    assert coffee.bag_size == "250g"
    assert coffee.price_cents == 2300
    assert coffee.tasting_notes == ["bergamot", "clementine", "lavender", "blueberries"]


def test_colorfull_allows_products_without_type_or_tags() -> None:
    """Colorfull's source configuration accepts products without coffee tags."""
    product = {"handle": "apple-crumble", "type": "", "tags": []}

    assert ColorfullScraper()._is_coffee_product(product)


def test_shopify_product_prefers_labeled_html_product_facts() -> None:
    """Product-page label sections beat less complete JSON description text."""
    product = {
        "title": "Apple Crumble",
        "price": 3200,
        "available": True,
        "type": "",
        "tags": [],
        "description": "<p>Process: Washed</p><p>Notes: Green Apple, Green Jolly Rancher</p>",
    }
    html = """
    <div class="mt-8 text-scheme-text">
      <ul>
        <li><span>Value / Roasting degree: 2 - Medium</span></li>
        <li><span>Process: Co-ferment and Ethyl Acetate Decaf</span></li>
        <li><span>Tasting notes: Maraschino Cherry + Strawberry Jam + Dark Chocolate</span></li>
      </ul>
    </div>
    """

    coffee = ColorfullScraper()._coffee_from_product(
        product,
        "https://colorfullcoffee.com/products/apple-crumble",
        html_soup=BeautifulSoup(html, "html.parser"),
    )

    assert coffee.process == "co-ferment and ethyl acetate decaf"
    assert coffee.roast_style == "2 - Medium"
    assert coffee.tasting_notes == ["maraschino cherry", "strawberry jam", "dark chocolate"]


def test_traffic_product_uses_shopify_json_labeled_description() -> None:
    """Traffic's Shopify JSON description contains the structured product facts."""
    product = {
        "title": "LITTLE SWAMPS AA",
        "handle": "little-swamps-aa",
        "price": 2600,
        "available": True,
        "type": "coffee",
        "tags": [],
        "description": (
            "<p><strong>Origin</strong><span>: </span><span>Kitale, Kenya<br></span></p>"
            "<p><span><strong>Process</strong>: Washed</span></p>"
            "<p><span><strong>Varietal</strong>: AA </span><span>Batian &amp; Ruiru</span></p>"
            "<p><span><strong>Roast level</strong>: Superlight</span></p>"
            "<p><span><strong>In the cup</strong>: tangerine, blackberry jam, raspberry</span></p>"
        ),
        "variants": [{"title": "Default Title", "weight": 300, "weight_unit": "g"}],
    }

    coffee = TrafficScraper()._coffee_from_product(
        product,
        "https://www.trafficcoffee.com/products/little-swamps-aa",
    )

    assert coffee.roaster == "Traffic Coffee"
    assert coffee.origin == "Kitale, Kenya"
    assert coffee.process == "washed"
    assert coffee.varietal == "AA Batian & Ruiru"
    assert coffee.roast_style == "Superlight"
    assert coffee.price_cents == 2600
    assert coffee.bag_size == "300g"
    assert coffee.tasting_notes == ["tangerine", "blackberry jam", "raspberry"]


def test_demello_product_uses_shopify_description_and_metafield_details() -> None:
    """De Mello's small quirks are handled by Shopify config and shared facts."""
    product = {
        "title": "Dancing Goats",
        "handle": "dancing-goats",
        "price": 1600,
        "available": True,
        "type": "Roasted Coffee Beans",
        "tags": ["_badge_SEASONAL"],
        "description": (
            '<p>Milk Chocolate<meta charset="utf-8"><span>&middot;</span> '
            '<meta charset="utf-8">Vanilla <meta charset="utf-8"><span>&middot;</span> '
            '<meta charset="utf-8">Dark Cherry<br></p>'
            '<p><meta charset="utf-8">Light <meta charset="utf-8">&#9679; &#9679; '
            '<meta charset="utf-8">&#9675;&#9675; &#9675; Dark</p>'
        ),
        "variants": [{"title": "227g", "weight": 0}],
    }
    html = (
        '<div class="metafield-rich_text_field">'
        '<p>Country : Brazil<br/>Region : Machado, Minas Gerais<br/>Producer : Group of Sitios<br/>'
        'Variety : Yellow Catuai<br/>Altitude : 1200 masl<br/>Process : Natural</p>'
        "</div>"
    )

    coffee = DeMelloScraper()._coffee_from_product(
        product,
        "https://hellodemello.com/products/dancing-goats",
        html_soup=BeautifulSoup(html, "html.parser"),
    )

    assert coffee.roaster == "De Mello Coffee"
    assert coffee.origin == "Brazil"
    assert coffee.producer == "Group of Sitios"
    assert coffee.process == "natural"
    assert coffee.varietal == "Yellow Catuai"
    assert coffee.altitude == "1200 masl"
    assert coffee.price_cents == 1600
    assert coffee.bag_size == "227g"
    assert coffee.tasting_notes == ["milk chocolate", "vanilla", "dark cherry"]
