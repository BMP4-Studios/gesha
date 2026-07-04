"""Tests for shared labeled product-fact extraction."""

from bs4 import BeautifulSoup
from gesha.parsers.common import extract_labeled_product_facts_from_html


def test_extract_labeled_product_facts_from_shopify_list_section() -> None:
    """Colorfull-style list rows map labels to catalog fields."""
    # Include an SVG icon to prove decorative markup is ignored.
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
    # Traffic splits labels and values across nested tags, which is common in themes.
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


def test_extract_labeled_product_facts_from_adjacent_div_grid() -> None:
    """Bare label/value grids map exact labels to catalog fields."""
    # House of Funk uses sibling divs without punctuation, so the shared parser
    # pairs exact known labels with the next visible sibling value.
    html = """
    <div class="coffee-info-grid">
      <div class="info-label">Origin</div>   <div class="info-value">Quindio,&nbsp;Colombia</div>
      <div class="info-label">Process</div>  <div class="info-value">Co-ferment Blend</div>
      <div class="info-label">Farm</div>     <div class="info-value">Multiple</div>
      <div class="info-label">Varietal</div> <div class="info-value">Variedad Colombia &amp; Castillo</div>
      <div class="info-label">Producer</div> <div class="info-value">Jairo Arcila &amp; Leonid Ramirez</div>
      <div class="info-label">Elevation</div><div class="info-value">1500-1800 masl</div>
    </div>
    """

    facts = extract_labeled_product_facts_from_html(BeautifulSoup(html, "html.parser"))

    assert facts["origin"] == "Quindio, Colombia"
    assert facts["process"] == "Co-ferment Blend"
    assert facts["producer"] == "Jairo Arcila & Leonid Ramirez"
    assert facts["varietal"] == "Variedad Colombia & Castillo"
    assert facts["altitude"] == "1500-1800 masl"
