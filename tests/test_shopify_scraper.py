"""Tests for behavior shared by JSON-backed Shopify scraper adapters."""

import logging

from bs4 import BeautifulSoup
from gesha.scrapers.shopify_scraper import (
    AngryRoasterScraper,
    ArteryScraper,
    ColorfullScraper,
    DeMelloScraper,
    EthicaScraper,
    HouseOfFunkScraper,
    KohiScraper,
    PorteBleueScraper,
    QuietlyScraper,
    RabbitHoleScraper,
    RogueWaveScraper,
    ShopifyScraper,
    SubtextScraper,
    TrafficScraper,
)


class JsonOptInTrafficScraper(TrafficScraper):
    """Traffic fixture scraper that opts into the collection JSON path."""

    USE_COLLECTION_JSON = True


class LocaleProductsIndexScraper(ShopifyScraper):
    """Fixture scraper for locale-prefixed Shopify product indexes."""

    BASE_URL = "https://cafepista.com/en"
    COLLECTION_URL = "https://cafepista.com/en/products"
    SOURCE_NAME = "Cafe Pista"
    ROASTER_NAME = "Cafe Pista"


class PaginatedFilterScraper(ShopifyScraper):
    """Fixture scraper that exercises pagination and new product filters."""

    BASE_URL = "https://example.com"
    COLLECTION_URL = "https://example.com/collections/coffee"
    SOURCE_NAME = "Example"
    ROASTER_NAME = "Example Roaster"
    PRODUCTS_JSON_LIMIT = 2
    INCLUDE_TAGS = ()
    INCLUDE_PRODUCT_TYPES = ("Coffee",)
    EXCLUDE_TAGS = ("wholesale-only",)
    SKIP_UNAVAILABLE_PRODUCTS = True


class FakeShopifyResponse:
    """Small response fixture for Shopify collection feed tests."""

    def __init__(
        self,
        json_data: dict | None = None,
        status_code: int = 200,
        text: str = "",
        headers: dict[str, str] | None = None,
        reason: str = "",
    ) -> None:
        """Create a response with optional JSON payload."""
        self._json_data = json_data
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self.reason = reason

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


def test_shopify_collection_json_preserves_locale_and_product_index_paths() -> None:
    """Locale storefronts keep /en in JSON endpoints and product URLs."""
    scraper = LocaleProductsIndexScraper()

    assert scraper._collection_products_json_url(page=2) == "https://cafepista.com/en/products.json?limit=250&page=2"
    assert scraper._canonical_product_url("https://cafepista.com/en/products/el-cortijo") == (
        "https://cafepista.com/en/products/el-cortijo"
    )


def test_shopify_collection_extracts_locale_prefixed_product_urls() -> None:
    """Product-page scraping can discover links from locale-prefixed themes."""
    html = '<a href="/en/collections/frontpage/products/oh-fudge-yuki">Coffee</a>'

    urls = LocaleProductsIndexScraper().extract_product_urls(html)

    assert urls == ["https://cafepista.com/en/products/oh-fudge-yuki"]


def test_pilot_shopify_sources_use_expected_collection_json_urls() -> None:
    """New batch sources should keep their focused Shopify collection feeds."""
    cases = [
        (
            HouseOfFunkScraper,
            "https://www.houseoffunkbrewing.com/collections/coffee/products.json?limit=250&page=1",
        ),
        (RogueWaveScraper, "https://roguewavecoffee.ca/collections/coffee/products.json?limit=250&page=1"),
        (QuietlyScraper, "https://www.quietlycoffee.com/collections/our-coffee/products.json?limit=250&page=1"),
        (KohiScraper, "https://kohi.ca/en/collections/frontpage/products.json?limit=250&page=1"),
        (SubtextScraper, "https://www.subtext.coffee/collections/filter-coffee-beans/products.json?limit=250&page=1"),
        (
            ArteryScraper,
            "https://thearterycommunityroasters.com/collections/by-the-bag/products.json?limit=250&page=1",
        ),
        (EthicaScraper, "https://ethicaroasters.com/collections/filter-coffee/products.json?limit=250&page=1"),
        (
            RabbitHoleScraper,
            "https://www.rabbitholeroasters.com/collections/all-coffee/products.json?limit=250&page=1",
        ),
    ]

    assert [scraper_class()._collection_products_json_url() for scraper_class, _ in cases] == [
        expected_url for _, expected_url in cases
    ]


def test_shopify_scrape_defaults_to_collection_json_feed(monkeypatch) -> None:
    """Shopify scrapers use collection JSON by default to avoid collection-page challenges."""
    calls: list[str] = []

    def fake_get(url: str, *args, **kwargs) -> FakeShopifyResponse:
        """Return an empty collection feed and fail if product pages are requested."""
        calls.append(url)
        if url == "https://www.trafficcoffee.com/collections/coffee/products.json?limit=250&page=1":
            return FakeShopifyResponse({"products": []})
        raise AssertionError(f"Unexpected request: {url}")

    scraper = TrafficScraper()
    monkeypatch.setattr(scraper.session, "get", fake_get)

    coffees = scraper.scrape()

    assert coffees == []
    assert calls == ["https://www.trafficcoffee.com/collections/coffee/products.json?limit=250&page=1"]


def test_shopify_collection_json_paginates_and_applies_source_filters(monkeypatch) -> None:
    """Batch sources can page through collections while filtering noisy products."""
    calls: list[str] = []
    first_page = {
        "products": [
            {
                "title": "Good Coffee",
                "handle": "good-coffee",
                "product_type": "Coffee",
                "tags": [],
                "body_html": "<p>Notes: Peach, Mango</p>",
                "variants": [{"id": 1, "title": "250g", "price": "22.00", "grams": 250, "available": True}],
            },
            {
                "title": "Wholesale Coffee",
                "handle": "wholesale-coffee",
                "product_type": "Coffee",
                "tags": ["wholesale-only"],
                "variants": [{"id": 2, "title": "250g", "price": "20.00", "grams": 250, "available": True}],
            },
        ]
    }
    second_page = {
        "products": [
            {
                "title": "Sold Out Coffee",
                "handle": "sold-out-coffee",
                "product_type": "Coffee",
                "tags": [],
                "variants": [{"id": 3, "title": "250g", "price": "20.00", "grams": 250, "available": False}],
            }
        ]
    }

    def fake_get(url: str, *args, **kwargs) -> FakeShopifyResponse:
        """Return two Shopify JSON pages and fail on unexpected pagination."""
        calls.append(url)
        if url == "https://example.com/collections/coffee/products.json?limit=2&page=1":
            return FakeShopifyResponse(first_page)
        if url == "https://example.com/collections/coffee/products.json?limit=2&page=2":
            return FakeShopifyResponse(second_page)
        raise AssertionError(f"Unexpected request: {url}")

    scraper = PaginatedFilterScraper()
    monkeypatch.setattr(scraper.session, "get", fake_get)

    coffees = scraper.scrape()

    assert calls == [
        "https://example.com/collections/coffee/products.json?limit=2&page=1",
        "https://example.com/collections/coffee/products.json?limit=2&page=2",
    ]
    assert len(coffees) == 1
    assert coffees[0].name == "good coffee"
    assert coffees[0].url == "https://example.com/products/good-coffee"
    assert coffees[0].tasting_notes == ["peach", "mango"]


def test_shopify_scrape_can_opt_into_collection_json_feed(monkeypatch) -> None:
    """Opted-in sources can read one collection JSON feed, not each product page."""
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

    scraper = JsonOptInTrafficScraper()
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

    scraper = JsonOptInTrafficScraper()
    monkeypatch.setattr(scraper.session, "get", fake_get)

    coffees = scraper.scrape()

    assert coffees == []
    assert calls == ["https://www.trafficcoffee.com/collections/coffee/products.json?limit=250&page=1"]


def test_shopify_collection_json_failure_logs_summary_and_full_response(monkeypatch, caplog) -> None:
    """The CLI warning stays short while the log file can keep response details."""
    headers = {
        "Retry-After": "120",
        "x-request-id": "request-123",
        "cf-ray": "ray-456-YUL",
        "shopify-complexity-score": "950",
        "shopify-complexity-score-v2": "95",
        "set-cookie": "diagnostic-cookie=value",
    }

    def fake_get(url: str, *args, **kwargs) -> FakeShopifyResponse:
        """Return a detailed 429 response from the collection feed."""
        return FakeShopifyResponse(
            status_code=429,
            reason="Too Many Requests",
            headers=headers,
            text="<html>blocked by storefront</html>",
        )

    scraper = JsonOptInTrafficScraper()
    monkeypatch.setattr(scraper.session, "get", fake_get)

    with caplog.at_level(logging.DEBUG):
        coffees = scraper.scrape()

    assert coffees == []
    assert (
        "Failed to fetch Shopify collection JSON for Traffic: HTTP 429 Too Many Requests, "
        "Retry-After: 120, request-id: request-123, cf-ray: ray-456-YUL, complexity: 950, complexity-v2: 95"
        in caplog.text
    )
    assert "Full HTTP failure while attempting to fetch Shopify collection JSON for Traffic" in caplog.text
    assert "set-cookie: diagnostic-cookie=value" in caplog.text
    assert "Body:\n<html>blocked by storefront</html>" in caplog.text


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
    # This fixture uses label aliases that differ from internal field names.
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
    # Colorfull opts out of tag requirements because its product tags are sparse.
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
    # Colorfull leaves dash parsing disabled, so the full title remains the name.
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
    # The pipe boundary is considered safe enough for all Shopify sources.
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


def test_rogue_wave_product_page_taste_list_supplies_tasting_notes() -> None:
    """Rogue Wave renders notes as product-page list items outside JSON facts."""
    product = {
        "title": "Test Coffee",
        "handle": "test-coffee",
        "price": 2500,
        "available": True,
        "type": "Coffee",
        "tags": ["coffee"],
        "description": "",
        "variants": [{"id": 123, "title": "250g", "price": 2500, "grams": 250, "available": True}],
    }
    html = """
    <div class="product-taste">
      <ul class="product-taste-list">
        <li class="peach">Peach</li>
        <li class="milk-chocolate">Milk Chocolate</li>
        <li class="apple">Apple</li>
        <li class="almond">Almond</li>
        <li class="tangerine">Tangerine</li>
      </ul>
    </div>
    """

    coffee = RogueWaveScraper()._coffee_from_product(
        product,
        "https://roguewavecoffee.ca/products/test-coffee",
        html_soup=BeautifulSoup(html, "html.parser"),
    )

    assert coffee.tasting_notes == ["peach", "milk chocolate", "apple", "almond", "tangerine"]


def test_house_of_funk_short_description_supplies_tasting_notes() -> None:
    """House of Funk notes live in a short product-page blurb."""
    product = {
        "title": "Sunday Morning",
        "handle": "sunday-morning",
        "price": 2200,
        "available": True,
        "type": "Coffee Beans",
        "tags": ["Coffee"],
        "description": "",
        "variants": [{"id": 123, "title": "250g", "price": 2200, "grams": 250, "available": True}],
    }
    html = """
    <div class="product-item__short-desc text-size--small">
      <span class="text-color--opacity">
        Caramelized banana, brown sugar, and warm spice. Bold, funky, and built like a morning hug.
      </span>
    </div>
    """

    coffee = HouseOfFunkScraper()._coffee_from_product(
        product,
        "https://www.houseoffunkbrewing.com/products/sunday-morning",
        html_soup=BeautifulSoup(html, "html.parser"),
    )

    assert coffee.tasting_notes == [
        "caramelized banana",
        "brown sugar",
        "warm spice",
        "bold",
        "funky",
        "built like a morning hug",
    ]


def test_traffic_product_uses_labeled_json_description_without_trailing_blurb() -> None:
    """Traffic collection JSON facts come from labeled HTML rows, not trailing prose."""
    # The trailing paragraphs should stop fact extraction before brewing advice.
    product = {
        "title": "Milkshake Espresso",
        "handle": "milkshakeespresso",
        "price": 2800,
        "available": True,
        "type": "coffee",
        "tags": [],
        "description": (
            "<p><strong>Origin</strong><span>: Kenya &amp; Ethiopia </span><span><br></span></p>"
            "<p><span><strong>Process</strong>: washed &amp; natural</span></p>"
            "<p><span><strong>Altitude</strong>: ~1700</span><span>-2200m</span></p>"
            "<p><span><strong>Varietal</strong>: various JARC Landraces &amp; combination of SL's and ruiru 11, "
            "Batian</span><span><br></span></p>"
            "<p><strong>Roast level: </strong>Medium</p>"
            "<p><span><strong>Notes</strong>: upside down pineapple cake, raspberry, peach<br></span></p>"
            "<p>Originally an ode to one of our favourite espresso blends from the UK, the milkshake morphed into "
            "our tribute to a director that we love...David Lynch.</p>"
            "<p><strong>PULLING THE MILKSHAKE</strong></p>"
            "<p>We recommend larger shots, so, a larger ratio of dry to wet.</p>"
        ),
        "variants": [{"title": "Default Title", "weight": 300, "weight_unit": "g"}],
    }

    coffee = TrafficScraper()._coffee_from_product(
        product,
        "https://www.trafficcoffee.com/products/milkshakeespresso",
    )

    assert coffee.roaster == "Traffic Coffee"
    assert coffee.origin == "kenya ethiopia"
    assert coffee.process == "washed natural"
    assert coffee.varietal == "various JARC Landraces & combination of SL's and ruiru 11, Batian"
    assert coffee.altitude == "~1700 -2200m"
    assert coffee.roast_style == "Medium"
    assert coffee.price_cents == 2800
    assert coffee.bag_size == "300g"
    assert coffee.tasting_notes == ["upside down pineapple cake", "raspberry", "peach"]


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
