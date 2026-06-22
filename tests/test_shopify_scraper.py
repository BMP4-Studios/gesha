"""Tests for behavior shared by JSON-backed Shopify scraper adapters."""

import logging

from bs4 import BeautifulSoup
from gesha.scrapers.shopify_scraper import (
    AngryRoasterScraper,
    ArteryScraper,
    CafePistaScraper,
    Celcius94Scraper,
    ColorfullScraper,
    DeMelloScraper,
    EscapeScraper,
    EthicaScraper,
    HouseOfFunkScraper,
    JungleScraper,
    KohiScraper,
    MonogramScraper,
    NarvalScraper,
    NektarScraper,
    PiratesScraper,
    PorteBleueScraper,
    QuietlyScraper,
    RabbitHoleScraper,
    RogueWaveScraper,
    SeptemberScraper,
    ShopifyScraper,
    SubtextScraper,
    TrafficScraper,
    ZaAndKloScraper,
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
        (EscapeScraper, "https://escape.cafe/collections/coffees/products.json?limit=250&page=1"),
        (PiratesScraper, "https://piratesofcoffee.com/collections/all-coffee/products.json?limit=250&page=1"),
        (Celcius94Scraper, "https://94celcius.com/en/collections/cafes/products.json?limit=250&page=1"),
        (CafePistaScraper, "https://cafepista.com/en/collections/sacs/products.json?limit=250&page=1"),
        (
            JungleScraper,
            "https://junglelivraisoncafe.com/collections/les-melanges/products.json?limit=250&page=1",
        ),
        (ZaAndKloScraper, "https://zaandklo.com/products.json?limit=250&page=1"),
        (NektarScraper, "https://nektar.ca/en/collections/tous-les-cafes/products.json?limit=250&page=1"),
        (SeptemberScraper, "https://september.coffee/collections/coffee/products.json?limit=250&page=1"),
        (MonogramScraper, "https://monogramcoffee.com/collections/all-coffees/products.json?limit=250&page=1"),
        (NarvalScraper, "https://narval.cafe/en/collections/340g/products.json?limit=250&page=1"),
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


def test_artery_excludes_collection_apparel_by_handle() -> None:
    """Artery's bag collection can include apparel with no coffee facts."""
    product = {"handle": "artery-screen-printed-shirt", "type": "", "tags": []}

    assert not ArteryScraper()._is_coffee_product(product)


def test_rabbit_hole_excludes_experience_boxes_by_tag() -> None:
    """Rabbit Hole tasting boxes are bundles, not a single cart-optimized bag."""
    product = {"handle": "the-curious-rabbit-box", "type": "Coffee", "tags": ["All Coffee", "experience boxes"]}

    assert not RabbitHoleScraper()._is_coffee_product(product)


def test_next_batch_filters_non_bag_products_from_noisy_collections() -> None:
    """New Shopify sources keep bundles and adjacent products out of carts."""
    assert not PiratesScraper()._is_coffee_product(
        {"handle": "treasure-box-brazil-crew-essentials", "type": "Coffee Beans", "tags": []}
    )
    assert not ZaAndKloScraper()._is_coffee_product(
        {"handle": "roasters-box-espresso", "type": "coffee", "tags": []}
    )
    assert not NektarScraper()._is_coffee_product(
        {"handle": "ensemble-decouverte-origine", "type": "Cafés", "tags": []}
    )


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


def test_house_of_funk_coffee_info_grid_supplies_product_facts() -> None:
    """House of Funk's coffee-info grid feeds the shared fact parser."""
    product = {
        "title": "Banana French Toast",
        "handle": "banana-french-toast",
        "price": 2300,
        "available": True,
        "type": "Coffee Beans",
        "tags": ["Coffee"],
        "description": "",
        "variants": [{"id": 123, "title": "250g", "price": 2300, "grams": 250, "available": True}],
    }
    html = """
    <div class="coffee-info-section">
      <div class="coffee-info-grid">
        <div class="tasting-notes-wrapper">
          <span class="info-value-tasting-notes">Banana French Toast.</span>
        </div>
        <div class="info-label">Origin</div>   <div class="info-value">Quindio,&nbsp;Colombia</div>
        <div class="info-label">Process</div>  <div class="info-value">Co-ferment Blend</div>
        <div class="info-label">Farm</div>     <div class="info-value">Multiple</div>
        <div class="info-label">Varietal</div> <div class="info-value">Variedad Colombia &amp; Castillo</div>
        <div class="info-label">Producer</div> <div class="info-value">Jairo Arcila &amp; Leonid Ramirez</div>
        <div class="info-label">Elevation</div><div class="info-value">1500-1800 masl</div>
      </div>
    </div>
    """

    coffee = HouseOfFunkScraper()._coffee_from_product(
        product,
        "https://www.houseoffunkbrewing.com/products/banana-french-toast",
        html_soup=BeautifulSoup(html, "html.parser"),
    )

    assert coffee.origin == "quindio, colombia"
    assert coffee.process == "co-ferment blend"
    assert coffee.producer == "Jairo Arcila & Leonid Ramirez"
    assert coffee.varietal == "Variedad Colombia & Castillo"
    assert coffee.altitude == "1500-1800 masl"
    assert coffee.tasting_notes == ["banana french toast"]


def test_common_shopify_caption_selector_supplies_tasting_notes() -> None:
    """Shared Shopify caption markup feeds the same selector note extractor."""
    product = {
        "title": "Caption Coffee",
        "handle": "caption-coffee",
        "price": 2400,
        "available": True,
        "type": "Coffee",
        "tags": ["coffee"],
        "description": "",
        "variants": [{"id": 123, "title": "250g", "price": 2400, "grams": 250, "available": True}],
    }
    html = """
    <p class="product__text inline-richtext caption-with-letter-spacing">
      Peach, honey, jasmine
    </p>
    """

    coffee = AngryRoasterScraper()._coffee_from_product(
        product,
        "https://theangryroaster.com/products/caption-coffee",
        html_soup=BeautifulSoup(html, "html.parser"),
    )

    assert coffee.tasting_notes == ["peach", "honey", "jasmine"]


def test_escape_product_page_accordion_supplies_scoped_facts() -> None:
    """Escape facts come from the product-page bean accordion."""
    product = {
        "title": "Mayor - Laos",
        "handle": "mayor-laos",
        "price": 2400,
        "available": True,
        "type": "Coffee",
        "tags": [],
        "description": "<p>Long story without specs.</p>",
        "variants": [{"id": 123, "title": "300g", "price": 2400, "grams": 300, "available": True}],
    }
    html = """
    <p class="productHero__ingredients t-h2">Bosc Pear, Glossette, Brown Sugar</p>
    <div id="ProductAccordion-beans" class="content t-body">
      <div>Type: Single Origin</div>
      <div>Notes: Bosc Pear, Glossette, Brown Sugar</div>
      <div>Country: Laos</div>
      <div>Region: Champasak Province, Bolaven Plateau</div>
      <div>Process: Washed</div>
      <div>Varieties: Catigua</div>
      <div>Altitude: 800-1350 m</div>
    </div>
    <div><p>Country: Kenya</p><p>Process: Natural</p></div>
    """

    coffee = EscapeScraper()._coffee_from_product(
        product,
        "https://escape.cafe/products/mayor-laos",
        html_soup=BeautifulSoup(html, "html.parser"),
    )

    assert coffee.origin == "laos"
    assert coffee.process == "washed"
    assert coffee.varietal == "Catigua"
    assert coffee.altitude == "800-1350 m"
    assert coffee.tasting_notes == ["bosc pear", "glossette", "brown sugar"]


def test_cafe_pista_rte_description_supplies_product_facts() -> None:
    """Cafe Pista uses an RTE product-description block for visible specs."""
    product = {
        "title": "El Cortijo",
        "handle": "el-cortijo",
        "price": 2650,
        "available": True,
        "type": "Sac de café",
        "tags": [],
        "description": "<p>Generic collection teaser.</p>",
        "variants": [{"id": 123, "title": "300G", "price": 2650, "grams": 300, "available": True}],
    }
    html = """
    <rte-formatter class="spacing-style text-block rte rte">
      <p>
        Region : Nariño, Colombie
        Farm : Ximena Cifuentes
        Variety: Caturra, Colombia, Castillo
        Altitude : 2100 M
        Method: Washed
        Notes: Apple, citrus, caramel
      </p>
    </rte-formatter>
    <div><p>Region : Wrong carousel text</p></div>
    """

    coffee = CafePistaScraper()._coffee_from_product(
        product,
        "https://cafepista.com/en/products/el-cortijo",
        html_soup=BeautifulSoup(html, "html.parser"),
    )

    assert coffee.origin == "nariño, colombie"
    assert coffee.producer == "Ximena Cifuentes"
    assert coffee.process == "washed"
    assert coffee.varietal == "Caturra, Colombia, Castillo"
    assert coffee.altitude == "2100 M"
    assert coffee.tasting_notes == ["apple", "citrus", "caramel"]


def test_94_celcius_leading_note_fallbacks_supply_notes() -> None:
    """Short note headings and x-separated note lines are accepted fallbacks."""
    decaf = {
        "title": "Decaf Colombia",
        "handle": "decaf-colombie",
        "price": 2499,
        "available": True,
        "type": "Coffee",
        "tags": [],
        "description": "<p>Banana Bread x Apple x Dark Chocolate</p><p>Region: Tolima</p><p>Process: Washed</p>",
        "variants": [{"id": 123, "title": "300g", "price": 2499, "grams": 300, "available": True}],
    }
    caro = {
        "title": "Caro Citric",
        "handle": "caro-citric-colombie",
        "price": 3200,
        "available": True,
        "type": "Coffee",
        "tags": [],
        "description": (
            "<p>In the cup</p><p>🍊 Fresh Tangerine</p><p>Milk Chocolate</p><p>Creamy</p>"
            "<p>A bright and juicy cup, where citrus brings freshness.</p>"
            "<p>Region: Andes, Antioquia, Colombia</p><p>Process: Natural</p>"
        ),
        "variants": [{"id": 124, "title": "300g", "price": 3200, "grams": 300, "available": True}],
    }

    decaf_coffee = Celcius94Scraper()._coffee_from_product(decaf, "https://94celcius.com/en/products/decaf-colombie")
    caro_coffee = Celcius94Scraper()._coffee_from_product(
        caro,
        "https://94celcius.com/en/products/caro-citric-colombie",
    )

    assert decaf_coffee.tasting_notes == ["banana bread", "apple", "dark chocolate"]
    assert caro_coffee.tasting_notes == ["fresh tangerine", "milk chocolate", "creamy"]


def test_monogram_product_text_stops_notes_before_cross_link() -> None:
    """Monogram note extraction stops before product recommendation links."""
    product = {
        "title": "Warmth Filter Blend",
        "handle": "warmth-filter-blend",
        "price": 2000,
        "available": True,
        "type": "Whole Bean",
        "tags": [],
        "description": "",
        "variants": [{"id": 123, "title": "300g", "price": 2000, "grams": 300, "available": True}],
    }
    html = """
    <div class="product__text rte text-base">
      <p>
        Chocolatey, rich and smooth.
        • Process: Washed
        • Variety: Blend
        • Origin: Central America, South America
        • Tasting Notes: Chocolate, Nougat
        <a href="/products/warmth-espresso-blend">Want this for espresso?</a>
      </p>
    </div>
    """

    coffee = MonogramScraper()._coffee_from_product(
        product,
        "https://monogramcoffee.com/products/warmth-filter-blend",
        html_soup=BeautifulSoup(html, "html.parser"),
    )

    assert coffee.origin == "central america, south america"
    assert coffee.process == "washed"
    assert coffee.varietal == "Blend"
    assert coffee.tasting_notes == ["chocolate", "nougat"]


def test_narval_description_leading_weight_supplies_bag_size() -> None:
    """Narval can recover bag size when Shopify variants report zero grams."""
    product = {
        "title": "Flybine Espresso",
        "handle": "flybine",
        "price": 2400,
        "available": True,
        "type": "Coffee",
        "tags": [],
        "description": "<p>340g</p><p>Tasting notes: Chocolate – almond - cherry</p>",
        "variants": [{"id": 123, "title": "Default Title", "price": 2400, "grams": 0, "available": True}],
    }

    coffee = NarvalScraper()._coffee_from_product(product, "https://narval.cafe/en/products/flybine")

    assert coffee.bag_size == "340g"
    assert coffee.tasting_notes == ["chocolate", "almond", "cherry"]


def test_subtext_product_page_supplies_shogun_specs_and_meta_notes() -> None:
    """Subtext combines page-rendered specs with SEO/meta tasting notes."""
    product = {
        "title": "Ethiopia Chelbesa Danche, Washed Kurume & Wolisho",
        "handle": "ethiopia-chelbesa-danche-washed-kurume-wolisho",
        "price": 2700,
        "available": True,
        "type": "Coffee",
        "tags": [],
        # The collection JSON body can be generic shipping text, so page
        # hydration has to supply the coffee-specific metadata.
        "description": "<p>Orders are roasted and shipped weekly.</p>",
        "variants": [{"id": 123, "title": "250g", "price": 2700, "grams": 250, "available": True}],
    }
    html = """
    <meta name="description"
      content="Espresso roasted coffee beans from SNAP in Gedeb, Ethiopia with tasting notes of jasmine, white cherry and peach nectar.">
    <div class="shg-rich-text shg-default-text-content">
      <p><span>Producers SNAP &amp; Smallholders of Chelbesa</span></p>
      <p><span>Station &nbsp; &nbsp; &nbsp; Chelbesa Danche</span></p>
      <p><span>Region &nbsp; &nbsp; &nbsp; Chelbesa, Gedeb, Gedeo, Ethiopia</span></p>
      <p><span>Harvest &nbsp; &nbsp; &nbsp; December '25-January '26</span></p>
      <p><span>Varieties &nbsp; &nbsp; Kurume &amp; Wolisho</span></p>
      <p><span>Process &nbsp; &nbsp; &nbsp; Washed</span></p>
      <p><span>Altitude &nbsp; &nbsp; &nbsp; 2,200 masl</span></p>
      <p><span>Importer &nbsp; &nbsp; Quest</span></p>
    </div>
    """

    coffee = SubtextScraper()._coffee_from_product(
        product,
        "https://www.subtext.coffee/products/ethiopia-chelbesa-danche-washed-kurume-wolisho",
        html_soup=BeautifulSoup(html, "html.parser"),
    )

    assert coffee.origin == "chelbesa, gedeb, gedeo, ethiopia"
    assert coffee.producer == "SNAP & Smallholders of Chelbesa"
    assert coffee.process == "washed"
    assert coffee.varietal == "Kurume & Wolisho"
    assert coffee.altitude == "2,200 masl"
    assert coffee.tasting_notes == ["jasmine", "white cherry", "peach nectar"]


def test_rabbit_hole_description_impressions_and_location_labels_supply_facts() -> None:
    """Rabbit Hole descriptions use Impressions and Country/Location labels."""
    product = {
        "title": "Ixhuatlan Mexico Washed",
        "handle": "ixhuatlan-mexico-washed",
        "price": 2400,
        "available": True,
        "type": "Coffee",
        "tags": ["All Coffee"],
        "description": (
            "<p>Impressions: cordial cherry, rustic cacao, baked apple, cajeta<br>"
            "Roast degree: medium (3/5)<br>"
            "Country: Mexico<br>"
            "Location: Matlaquiahuitl, Ixhualtlán del café (Veracruz)<br>"
            "Variety: mixed, field blend<br>"
            "Process: Washed<br>"
            "Farm: Alere &amp; Abuntia Coop.<br>"
            "Farmer: Adalberto Campailla<br>"
            "Import partner: Semilla</p>"
        ),
        "variants": [{"id": 123, "title": "250g", "price": 2400, "grams": 250, "available": True}],
    }

    coffee = RabbitHoleScraper()._coffee_from_product(
        product,
        "https://www.rabbitholeroasters.com/products/ixhuatlan-mexico-washed",
    )

    assert coffee.origin == "mexico"
    assert coffee.process == "washed"
    assert coffee.producer == "Alere & Abuntia Coop."
    assert coffee.varietal == "mixed, field blend"
    assert coffee.roast_style == "medium (3/5)"
    assert coffee.tasting_notes == ["cordial cherry", "rustic cacao", "baked apple", "cajeta"]


def test_rabbit_hole_can_use_handle_process_when_description_omits_it() -> None:
    """Rabbit Hole sometimes keeps process in the handle instead of the body."""
    product = {
        "title": "Mengeshe Gumi",
        "handle": "mengeshe-gumi-yirgacheffe-natural",
        "price": 2450,
        "available": True,
        "type": "Coffee",
        "tags": ["All Coffee"],
        "description": (
            "<p>Impressions: Orange blossom, toffee, ground cherry, goji berry<br>"
            "Roast degree: light (2/5)<br>"
            "Country: Ethiopia<br>"
            "Region: Yirgacheffe (Worka, Sakaro)<br>"
            "Washing Station: Mengeshe Gumi<br>"
            "Variety: Kurume, Dega, Wolisho<br>"
            "Importer: Crop to Cup</p>"
        ),
        "variants": [{"id": 123, "title": "250g", "price": 2450, "grams": 250, "available": True}],
    }

    coffee = RabbitHoleScraper()._coffee_from_product(
        product,
        "https://www.rabbitholeroasters.com/products/mengeshe-gumi-yirgacheffe-natural",
    )

    assert coffee.origin == "ethiopia"
    assert coffee.process == "natural"
    assert coffee.varietal == "Kurume, Dega, Wolisho"
    assert coffee.tasting_notes == ["orange blossom", "toffee", "ground cherry", "goji berry"]


def test_ethica_best_after_label_stops_tasting_note_extraction() -> None:
    """Ethica notes should not absorb the adjacent Best After guidance."""
    product = {
        "title": "Ethica Test Coffee",
        "handle": "ethica-test-coffee",
        "price": 2300,
        "available": True,
        "type": "Coffee",
        "tags": [],
        "description": (
            "<p>Origin: Colombia</p>"
            "<p>Process: Washed</p>"
            "<p>Notes: Chocolate, Hazelnut, Stone Fruits<br>Best After: 2 weeks post-roasting</p>"
        ),
        "variants": [{"id": 123, "title": "250g", "price": 2300, "grams": 250, "available": True}],
    }

    coffee = EthicaScraper()._coffee_from_product(
        product,
        "https://ethicaroasters.com/products/ethica-test-coffee",
    )

    assert coffee.origin == "colombia"
    assert coffee.process == "washed"
    assert coffee.tasting_notes == ["chocolate", "hazelnut", "stone fruits"]


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


def test_quietly_description_spec_sheet_supplies_product_facts() -> None:
    """Quietly's JSON description spec sheet uses shared selector-scoped facts."""
    # Quietly nests story paragraphs and the compact spec sheet in matching
    # styled divs; REGION from the spec sheet should beat the earlier ORIGIN story.
    product = {
        "title": "DECAFFEINATED",
        "handle": "decaffeinated",
        "price": 2600,
        "available": True,
        "type": "Coffee",
        "tags": [],
        "description": (
            '<div style="text-align: left;">'
            '<p><strong>ORIGIN:<br></strong>'
            "I love bringing in fun decaf lots because I love great decaf! "
            "So could not say no to this tropical and fun lot from the Siane Organic Agriculture Cooperative "
            "located in the Chuave district within the province of Chimbu.</p>"
            '<p><strong>FLAVOUR:</strong><br>'
            "In the cup you can expect juicy citrus and malic acid.</p>"
            "</div>"
            '<div style="text-align: left;">'
            '<strong><span style="color: #00205b;">PARAMETERS:&nbsp;</span><br></strong>'
            "For espresso, use a 1:2.3 ratio in 32-35 seconds.<br>"
            '<div style="text-align: left;">'
            '<strong><span style="color: #00205b;">ROAST DEGREE:&nbsp;</span><br></strong>'
            "Light-Medium.<br>"
            '<div style="text-align: left;">'
            '<strong><span style="color: #00205b;">TASTE: <br></span></strong>'
            "Blackberry, Nectarine &amp; Oolong Tea.<br>"
            '<strong><span style="color: #00205b;">REGION:<br></span></strong>'
            "Chimbu Province.<br>"
            '<strong><span style="color: #00205b;">FARM:</span><br></strong>'
            "Siane Organic Agriculture Cooperative.<br>"
            '<strong><span style="color: #00205b;">VARIETY:</span><br></strong>'
            "Bourbon &amp; Typica.<br>"
            '<strong><span style="color: #00205b;">ELEVATION:</span><br></strong>'
            "1350m.<br>"
            '<strong><span style="color: #00205b;">PROCESS:</span><br></strong>'
            "Washed.<br>"
            '<strong><span style="color: #00205b;">IMPORTER:</span><br></strong>'
            "Rachel at Covoya.<br>"
            '<strong><span style="color: #00205b;">FOB&nbsp;PRICING:</span><br></strong>'
            "$13.40 USD per Kilogram.<br>"
            "</div>"
            "</div>"
            "</div>"
        ),
        "variants": [{"id": 123, "title": "300 Grams", "price": 2600, "grams": 300, "available": True}],
    }

    coffee = QuietlyScraper()._coffee_from_product(
        product,
        "https://www.quietlycoffee.com/products/decaffeinated",
    )

    assert coffee.origin == "chimbu province."
    assert coffee.producer == "Siane Organic Agriculture Cooperative."
    assert coffee.varietal == "Bourbon & Typica."
    assert coffee.altitude == "1350m."
    assert coffee.process == "washed."
    assert coffee.roast_style == "Light-Medium."
    assert coffee.tasting_notes == ["blackberry", "nectarine", "oolong tea"]


def test_quietly_nested_spec_sheet_wins_over_story_origin() -> None:
    """Nested Quietly spec-sheet facts should beat broader story wrappers."""
    # Sugar Mountain nests the compact TASTE/REGION block inside a larger div
    # that also contains an ORIGIN story, so deepest selector matches must win.
    product = {
        "title": "SUGAR MOUNTAIN",
        "handle": "sugar-mountain",
        "price": 2800,
        "available": True,
        "type": "Coffee",
        "tags": [],
        "description": (
            '<div style="text-align: left;">'
            '<strong><span style="color: #00205b;">ORIGIN:</span><br></strong>'
            "<p>Angel Ortega returns to our menu with a very fun passion fruit co-ferment. "
            "The grower initiative is frequently featured on the Quietly menu.</p>"
            '<div style="text-align: left;">'
            '<strong><span style="color: #00205b;">FLAVOUR:</span><br></strong>'
            "The cup is wonderfully sweet with marshmallow and cooked sugar notes."
            "</div>"
            '<div style="text-align: left;">'
            '<div style="text-align: left;">'
            '<strong><span style="color: #00205b;">ROAST DEGREE:&nbsp;</span><br></strong>'
            "Light-Medium.<br>"
            '<div style="text-align: left;">'
            '<strong><span style="color: #00205b;">TASTE:&nbsp;</span></strong><br>'
            "Passion Fruit, Mandarin Orange &amp; Marshmallow.<br>"
            '<strong><span style="color: #00205b;">REGION:</span><br></strong>'
            "Kennedy, San Agustin.<br>"
            '<strong><span style="color: #00205b;">FARM:</span><br></strong>'
            "Miramar.<br>"
            '<strong><span style="color: #00205b;">VARIETAL:</span><br></strong>'
            "Pink Bourbon.<br>"
            '<strong><span style="color: #00205b;">ELEVATION:</span><br></strong>'
            "1680m.<br>"
            '<strong><span style="color: #00205b;">PROCESS:</span><br></strong>'
            "Passion fruit co-ferment &amp; washed.<br>"
            '<strong><span style="color: #00205b;">IMPORTER:</span><br></strong>'
            "Brendan at Semilla.<br>"
            "</div>"
            "</div>"
            "</div>"
            "</div>"
        ),
        "variants": [{"id": 123, "title": "300 Grams", "price": 2800, "grams": 300, "available": True}],
    }

    coffee = QuietlyScraper()._coffee_from_product(
        product,
        "https://www.quietlycoffee.com/products/sugar-mountain",
    )

    assert coffee.origin == "kennedy, san agustin."
    assert coffee.producer == "Miramar."
    assert coffee.varietal == "Pink Bourbon."
    assert coffee.altitude == "1680m."
    assert coffee.process == "passion fruit co-ferment washed."
    assert coffee.roast_style == "Light-Medium."
    assert coffee.tasting_notes == ["passion fruit", "mandarin orange", "marshmallow"]


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
