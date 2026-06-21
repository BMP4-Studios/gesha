"""Tests for behavior shared by JSON-backed Shopify scraper adapters."""

from bs4 import BeautifulSoup
from gesha.scrapers.shopify_scraper import (
    AngryRoasterScraper,
    ColorfullScraper,
    DeMelloScraper,
    PorteBleueScraper,
    TrafficScraper,
)


class FakeShopifyResponse:
    """Small response fixture for Shopify collection feed tests."""

    def __init__(self, json_data: dict | None = None, status_code: int = 200, text: str = "") -> None:
        """Create a response with optional JSON payload."""
        self._json_data = json_data
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        """Mirror the HTTP failure behavior the scraper expects."""
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        """Return the configured JSON payload."""
        if self._json_data is None:
            raise ValueError("No JSON data configured")
        return self._json_data


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


def test_shopify_scrape_uses_collection_json_feed(monkeypatch) -> None:
    """The primary scrape path reads one collection JSON feed, not each product page."""
    calls: list[str] = []

    # This payload uses collection-feed field names so the adapter has to
    # normalize ``body_html``, ``product_type``, decimal prices, and variants.
    payload = {
        "products": [
            {
                "title": "Little Swamps AA",
                "handle": "little-swamps-aa",
                "product_type": "coffee",
                "tags": [],
                "body_html": (
                    "<p>Origin: Kitale, Kenya</p>"
                    "<p>Process: Washed</p>"
                    "<p>In the cup: tangerine, blackberry jam, raspberry</p>"
                ),
                "variants": [
                    {
                        "id": 123,
                        "title": "300g",
                        "price": "26.00",
                        "grams": 300,
                        "available": True,
                    }
                ],
            }
        ]
    }

    def fake_get(url: str, *args, **kwargs) -> FakeShopifyResponse:
        """Return the collection feed and fail if product pages are requested."""
        calls.append(url)
        if url == "https://www.trafficcoffee.com/collections/coffee/products.json?limit=250&page=1":
            return FakeShopifyResponse(payload)
        raise AssertionError(f"Unexpected request: {url}")

    scraper = TrafficScraper()
    monkeypatch.setattr(scraper.session, "get", fake_get)

    coffees = scraper.scrape()

    assert calls == ["https://www.trafficcoffee.com/collections/coffee/products.json?limit=250&page=1"]
    assert len(coffees) == 1
    assert coffees[0].name == "little swamps aa"
    assert coffees[0].url == "https://www.trafficcoffee.com/products/little-swamps-aa"
    assert coffees[0].origin == "kitale, kenya"
    assert coffees[0].process == "washed"
    assert coffees[0].price_cents == 2600
    assert coffees[0].bag_size == "300g"
    assert coffees[0].variants[0].shopify_variant_id == "123"
    assert coffees[0].tasting_notes == ["tangerine", "blackberry jam", "raspberry"]


def test_shopify_collection_json_rate_limit_does_not_fall_back_to_product_pages(monkeypatch) -> None:
    """A blocked collection feed stops cleanly instead of making many more requests."""
    calls: list[str] = []

    def fake_get(url: str, *args, **kwargs) -> FakeShopifyResponse:
        """Return a rate limit from the collection feed."""
        calls.append(url)
        return FakeShopifyResponse(status_code=429)

    scraper = TrafficScraper()
    monkeypatch.setattr(scraper.session, "get", fake_get)

    coffees = scraper.scrape()

    assert coffees == []
    assert calls == ["https://www.trafficcoffee.com/collections/coffee/products.json?limit=250&page=1"]


def test_colorfull_scrape_uses_product_pages_for_richer_source_facts(monkeypatch) -> None:
    """Colorfull opts out of collection JSON because those feeds omit useful facts."""
    calls: list[str] = []

    # Colorfull's useful facts live in product-page HTML, not the collection feed.
    collection_html = '<a href="/products/apple-fritter-blend">Apple Fritter</a>'
    product_html = """
    <div class="mt-8 text-scheme-text">
      <ul>
        <li><span>Process: Natural</span></li>
        <li><span>Tasting notes: Candied Apple - Cinnamon - Green Jolly Rancher</span></li>
      </ul>
    </div>
    """
    product_payload = {
        "title": "Apple Fritter - Blend",
        "handle": "apple-fritter-blend",
        "price": 3400,
        "available": True,
        "type": "",
        "tags": [],
        "description": "",
        "variants": [{"id": 133, "title": "250g", "price": 3400, "available": True}],
    }

    def fake_get(url: str, *args, **kwargs) -> FakeShopifyResponse:
        """Return old-path responses and fail if collection JSON is requested."""
        calls.append(url)

        # This assertion is the important part of the test: Colorfull should use
        # the old collection HTML -> product page -> .js path.
        if "products.json" in url:
            raise AssertionError(f"Unexpected collection JSON request: {url}")
        if url == "https://colorfullcoffee.com/collections/all":
            return FakeShopifyResponse(text=collection_html)
        if url == "https://colorfullcoffee.com/products/apple-fritter-blend":
            return FakeShopifyResponse(text=product_html)
        if url == "https://colorfullcoffee.com/products/apple-fritter-blend.js":
            return FakeShopifyResponse(product_payload)
        raise AssertionError(f"Unexpected request: {url}")

    scraper = ColorfullScraper()
    monkeypatch.setattr(scraper.session, "get", fake_get)

    coffees = scraper.scrape()

    assert calls == [
        "https://colorfullcoffee.com/collections/all",
        "https://colorfullcoffee.com/products/apple-fritter-blend",
        "https://colorfullcoffee.com/products/apple-fritter-blend.js",
    ]
    assert len(coffees) == 1
    assert coffees[0].name == "apple fritter - blend"
    assert coffees[0].process == "natural"
    assert coffees[0].tasting_notes == ["candied apple", "cinnamon", "green jolly rancher"]


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
    assert coffee.name == "colombia - gesha - inza"
    assert coffee.origin == "cauca, colombia"
    assert coffee.producer == "RAFAEL VELASQUEZ"
    assert coffee.process == "washed"
    assert coffee.varietal == "GESHA"
    assert coffee.altitude == "1900 MASL"
    assert coffee.bag_size == "250g"
    assert coffee.price_cents == 2300
    assert coffee.tasting_notes == ["bergamot", "clementine", "lavender", "blueberries"]


def test_shopify_product_defaults_to_smallest_available_variant() -> None:
    """Product-level display fields follow the lightest purchasable bag."""
    # Put the larger bag first to prove the scraper sorts by weight, not source order.
    product = {
        "title": "Smallest Bag",
        "price": 2600,
        "available": True,
        "tags": ["coffee"],
        "description": "",
        "variants": [
            {
                "id": 222,
                "title": "2lb",
                "price": 6000,
                "weight": 2,
                "weight_unit": "lb",
                "available": True,
            },
            {
                "id": 111,
                "title": "300g",
                "price": 2600,
                "weight": 300,
                "weight_unit": "g",
                "available": True,
            },
        ],
    }

    coffee = AngryRoasterScraper()._coffee_from_product(
        product,
        "https://theangryroaster.com/products/smallest-bag",
    )

    assert coffee.price_cents == 2600
    assert coffee.bag_size == "300g"
    assert [variant.shopify_variant_id for variant in coffee.variants] == ["222", "111"]
    assert [variant.weight_grams for variant in coffee.variants] == [907, 300]


def test_colorfull_allows_products_without_type_or_tags() -> None:
    """Colorfull's source configuration accepts products without coffee tags."""
    product = {"handle": "apple-crumble", "type": "", "tags": []}

    assert ColorfullScraper()._is_coffee_product(product)


def test_shopify_product_prefers_labeled_html_product_facts() -> None:
    """Product-page label sections beat less complete JSON description text."""
    # JSON says "Washed"; the product page says the richer Colorfull process.
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


def test_shopify_title_dash_facts_are_opt_in() -> None:
    """Dash-only titles are too ambiguous to parse without source config."""
    product = {
        "title": "Apple Crumble - Washed",
        "price": 3200,
        "available": True,
        "type": "",
        "tags": [],
        "description": "",
    }

    coffee = ColorfullScraper()._coffee_from_product(
        product,
        "https://colorfullcoffee.com/products/apple-crumble",
    )

    assert coffee.name == "apple crumble - washed"
    assert coffee.origin is None
    assert coffee.process is None


def test_shopify_title_pipe_facts_remain_supported() -> None:
    """Pipe-separated titles can still provide safe origin and process hints."""
    product = {
        "title": "Colombia - Las Flores | Washed",
        "price": 2300,
        "available": True,
        "type": "Coffee",
        "tags": ["coffee"],
        "description": "",
    }

    coffee = AngryRoasterScraper()._coffee_from_product(
        product,
        "https://theangryroaster.com/products/colombia-las-flores",
    )

    assert coffee.name == "colombia - las flores | washed"
    assert coffee.origin == "colombia"
    assert coffee.process == "washed"


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
    assert coffee.origin == "kitale, kenya"
    assert coffee.process == "washed"
    assert coffee.varietal == "AA Batian & Ruiru"
    assert coffee.roast_style == "Superlight"
    assert coffee.price_cents == 2600
    assert coffee.bag_size == "300g"
    assert coffee.tasting_notes == ["tangerine", "blackberry jam", "raspberry"]


def test_demello_product_uses_shopify_description_and_metafield_details() -> None:
    """De Mello's small quirks are handled by Shopify config and shared facts."""
    # Description carries notes/roast hints while the metafield carries facts.
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
        "<p>Country : Brazil<br/>Region : Machado, Minas Gerais<br/>Producer : Group of Sitios<br/>"
        "Variety : Yellow Catuai<br/>Altitude : 1200 masl<br/>Process : Natural</p>"
        "</div>"
    )

    coffee = DeMelloScraper()._coffee_from_product(
        product,
        "https://hellodemello.com/products/dancing-goats",
        html_soup=BeautifulSoup(html, "html.parser"),
    )

    assert coffee.roaster == "De Mello Coffee"
    assert coffee.origin == "brazil"
    assert coffee.producer == "Group of Sitios"
    assert coffee.process == "natural"
    assert coffee.varietal == "Yellow Catuai"
    assert coffee.altitude == "1200 masl"
    assert coffee.price_cents == 1600
    assert coffee.bag_size == "227g"
    assert coffee.tasting_notes == ["milk chocolate", "vanilla", "dark cherry"]
