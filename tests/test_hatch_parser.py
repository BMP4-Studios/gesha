from gesha.parsers.hatch_parser import parse_hatch_collection, parse_hatch_product


def test_parse_hatch_collection_excludes_non_bag_products() -> None:
    html = (
        '<a href="/shop/andres-martinez-geisha-washed">Coffee</a>'
        '<a href="/shop/hario-v60-filters">Filters</a>'
        '<a href="/shop/the-physics-of-espresso-book">Book</a>'
        '<a href="/shop/nitro-cold-brew">Cold Brew</a>'
        '<a href="/shop/berry-jam">Concentrate</a>'
        '<a href="/shop/non-alcoholic-german-bock">Drink</a>'
    )

    urls = parse_hatch_collection(html, base_url="https://hatchcrafted.com")

    assert urls == ["https://hatchcrafted.com/shop/andres-martinez-geisha-washed"]


def test_parse_hatch_collection_extracts_embedded_paths() -> None:
    html = (
        '{"href":"/shop/andres-martinez-geisha-washed"}'
        '{"href":"\\/shop\\/rio-brilhante-tropicana-natural"}'
        '"url":"/shop/blackout"'
        '{"href":"/shop/hario-v60-filters"}'
    )

    urls = parse_hatch_collection(html, base_url="https://hatchcrafted.com")

    assert urls == [
        "https://hatchcrafted.com/shop/andres-martinez-geisha-washed",
        "https://hatchcrafted.com/shop/blackout",
        "https://hatchcrafted.com/shop/rio-brilhante-tropicana-natural",
    ]


def test_parse_hatch_product_uses_only_labeled_tasting_notes() -> None:
    html = (
        "<h1>Example Gesha Washed</h1>"
        "<p>Origin: Origin: Huila, Colombia</p>"
        "<p>Producer: Example Farm</p>"
        "<p>Process: Washed</p>"
        "<p>Reminds us of: jasmine, white tea, nectarine</p>"
        "<p>This is a long farm story that should not become a tasting note.</p>"
        "<span>CA$35.00</span>"
    )

    coffee = parse_hatch_product(html, "https://hatchcrafted.com/shop/example-gesha")

    assert coffee.origin == "Huila, Colombia"
    assert coffee.tasting_notes == ["jasmine", "nectarine", "white tea"]


def test_parse_hatch_product_does_not_fallback_to_description_as_notes() -> None:
    html = (
        "<h1>Example Coffee</h1>"
        "<p>Origin: Colombia</p>"
        "<p>Process: Washed</p>"
        "<p>This is a descriptive paragraph, not a list of tasting notes.</p>"
        "<span>CA$22.00</span>"
    )

    coffee = parse_hatch_product(html, "https://hatchcrafted.com/shop/example-coffee")

    assert coffee.tasting_notes == []
