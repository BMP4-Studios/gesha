"""Tests for shared labeled product-fact extraction."""

from bs4 import BeautifulSoup

from gesha.parsers.common import extract_labeled_product_facts_from_html


def test_extract_labeled_product_facts_from_shopify_list_section() -> None:
    """Colorfull-style list rows map labels to catalog fields."""
    html = """
    <div class="mt-8 text-scheme-text">
      <ul>
        <li><svg><path></path></svg><span>Process: Co-ferment and Ethyl Acetate Decaf</span></li>
        <li><span>TasTinG NoTes: Maraschino Cherry + Strawberry Jam + Dark Chocolate</span></li>
      </ul>
    </div>
    """

    facts = extract_labeled_product_facts_from_html(BeautifulSoup(html, "html.parser"))

    assert facts["process"] == "Co-ferment and Ethyl Acetate Decaf"
    assert facts["tasting_notes"] == "Maraschino Cherry + Strawberry Jam + Dark Chocolate"


def test_extract_labeled_product_facts_from_traffic_paragraph_section() -> None:
    """Traffic-style strong labels and spans are parsed from product HTML."""
    html = """
    <div class="product-block-description">
      <p><strong>Origin</strong><span>: </span><span>Kitale, Kenya<br></span></p>
      <p><span><strong>Process</strong>: Washed</span></p>
      <p><span><strong>Varietal</strong>: AA </span><span>Batian &amp; Ruiru</span></p>
      <p><span><strong>Roast level</strong>: Superlight</span></p>
      <p><span><strong>In the cup</strong>: tangerine, blackberry jam, raspberry</span></p>
    </div>
    """

    facts = extract_labeled_product_facts_from_html(BeautifulSoup(html, "html.parser"))

    assert facts["origin"] == "Kitale, Kenya"
    assert facts["process"] == "Washed"
    assert facts["varietal"] == "AA Batian & Ruiru"
    assert facts["roast_style"] == "Superlight"
    assert facts["tasting_notes"] == "tangerine, blackberry jam, raspberry"
