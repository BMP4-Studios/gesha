"""Tests for behavior shared by JSON-backed Shopify scraper adapters."""

from bs4 import BeautifulSoup

from gesha.scrapers.shopify_scraper import AngryRoasterScraper, ColorfullScraper, PorteBleueScraper


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
