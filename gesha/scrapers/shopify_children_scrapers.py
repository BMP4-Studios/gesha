"""ShopifyScraper subclasses for sources that require special treatment, which is all of them?"""

from bs4 import BeautifulSoup

from gesha.scrapers.shopify_scraper import DEFAULT_PRODUCT_FACT_STOP_LABELS, ShopifyScraper


class PorteBleueScraper(ShopifyScraper):
    """Shopify configuration for Porte Bleue products."""

    # These subclasses are mostly declarative: they tell the shared Shopify
    # scraper which storefront URL and source labels to use.
    USE_COLLECTION_JSON = False
    BASE_URL = "https://portebleue.ca"
    COLLECTION_URL = f"{BASE_URL}/collections/coffee"
    SOURCE_NAME = "Porte Bleue"
    ROASTER_NAME = "Porte Bleue"


class ColorfullScraper(ShopifyScraper):
    """Shopify configuration for Colorfull, whose products lack coffee tags."""

    # Colorfull's collection JSON omits tasting notes, so use the richer product-page path.
    # Its facts live in one themed rich-text block, which keeps page-wide text
    # from competing with the shared label/value parser.
    USE_COLLECTION_JSON = False
    BASE_URL = "https://colorfullcoffee.com"
    COLLECTION_URL = f"{BASE_URL}/collections/all"
    SOURCE_NAME = "Colorfull"
    ROASTER_NAME = "Colorfull Coffee"
    INCLUDE_TAGS = ()
    EXCLUDE_HANDLE_KEYWORDS = ("gift", "subscription")
    PRODUCT_FACT_SELECTORS = ("div.mt-8.text-scheme-text",)


class AngryRoasterScraper(ShopifyScraper):
    """Shopify configuration for The Angry Roaster products."""

    BASE_URL = "https://theangryroaster.com"
    COLLECTION_URL = f"{BASE_URL}/collections/coffee"
    SOURCE_NAME = "The Angry Roaster"
    ROASTER_NAME = "The Angry Roaster"
    INCLUDE_TAGS = ("coffee",)


class TrafficScraper(ShopifyScraper):
    """Shopify configuration for Traffic products."""

    # Traffic stores rich facts inside a product description block; the selector
    # prevents unrelated page text from being scanned first.
    BASE_URL = "https://www.trafficcoffee.com"
    COLLECTION_URL = f"{BASE_URL}/collections/coffee"
    SOURCE_NAME = "Traffic"
    ROASTER_NAME = "Traffic Coffee"
    INCLUDE_TAGS = ()
    PRODUCT_FACT_STOP_LABELS = (*DEFAULT_PRODUCT_FACT_STOP_LABELS, "ABOUT")
    PRODUCT_FACT_SELECTORS = ("div.product-block-description",)


class DeMelloScraper(ShopifyScraper):
    """Shopify configuration for De Mello products."""

    # De Mello uses a metafield block for origin/process details and has a few
    # non-coffee handles that should never enter the catalog.
    BASE_URL = "https://hellodemello.com"
    COLLECTION_URL = f"{BASE_URL}/collections/all-coffee"
    SOURCE_NAME = "De Mello"
    ROASTER_NAME = "De Mello Coffee"
    INCLUDE_TAGS = ()
    EXCLUDE_HANDLE_KEYWORDS = (*ShopifyScraper.EXCLUDE_HANDLE_KEYWORDS, "starter-kit", "instant-coffee")
    HYDRATE_COLLECTION_PRODUCTS = True
    PRODUCT_FACT_SELECTORS = ("div.metafield-rich_text_field",)


class HouseOfFunkScraper(ShopifyScraper):
    """Shopify configuration for House of Funk products."""

    # The coffee collection also exposes subscription and brew-gear products, so
    # use product type instead of the broad Coffee tag.
    # House of Funk keeps structured coffee facts in a bare label/value grid,
    # and notes can appear either there or in the two-sentence short blurb.
    BASE_URL = "https://www.houseoffunkbrewing.com"
    COLLECTION_URL = f"{BASE_URL}/collections/coffee"
    SOURCE_NAME = "House of Funk"
    ROASTER_NAME = "House of Funk"
    INCLUDE_TAGS = ()
    INCLUDE_PRODUCT_TYPES = ("Coffee Beans",)
    HYDRATE_COLLECTION_PRODUCTS = True
    PRODUCT_FACT_SELECTORS = ("div.coffee-info-grid",)
    TASTING_NOTE_TEXT_SELECTORS = (
        "div.coffee-info-grid span.info-value-tasting-notes",
        "div.product-item__short-desc span.text-color--opacity",
        *ShopifyScraper.TASTING_NOTE_TEXT_SELECTORS,
    )


class RogueWaveScraper(ShopifyScraper):
    """Shopify configuration for Rogue Wave products."""

    # Rogue Wave's collection JSON often omits notes that are rendered on the
    # product page as <ul class="product-taste-list"><li>...</li></ul>. Hydrate
    # product pages so those visible notes make it into cart keyword matching.
    BASE_URL = "https://roguewavecoffee.ca"
    COLLECTION_URL = f"{BASE_URL}/collections/coffee"
    SOURCE_NAME = "Rogue Wave"
    ROASTER_NAME = "Rogue Wave Coffee"
    INCLUDE_TAGS = ("coffee",)
    HYDRATE_COLLECTION_PRODUCTS = True
    TASTING_NOTE_SELECTORS = ("ul.product-taste-list li",)


class QuietlyScraper(ShopifyScraper):
    """Shopify configuration for Quietly products."""

    # Quietly's collection includes apparel/subscriptions, while coffee products
    # are consistently typed as Coffee.
    # Their JSON description contains a final inline-styled spec sheet; require
    # both TASTE and REGION so earlier origin/flavour story wrappers are ignored.
    BASE_URL = "https://www.quietlycoffee.com"
    COLLECTION_URL = f"{BASE_URL}/collections/our-coffee"
    SOURCE_NAME = "Quietly"
    ROASTER_NAME = "Quietly Coffee"
    INCLUDE_TAGS = ()
    INCLUDE_PRODUCT_TYPES = ("Coffee",)
    PRODUCT_FACT_STOP_LABELS = (*DEFAULT_PRODUCT_FACT_STOP_LABELS, "Importer", "FOB Pricing", "Years Partnered")
    PRODUCT_FACT_SELECTORS = (
        "div[style*='text-align: left']:has(strong span:-soup-contains('TASTE'))"
        ":has(strong span:-soup-contains('REGION'))",
    )


class KohiScraper(ShopifyScraper):
    """Shopify configuration for Kohi products."""

    # Kohi's English storefront keeps product types/tags sparse, so the focused
    # frontpage collection is the source boundary and handle/tag exclusions do cleanup.
    BASE_URL = "https://kohi.ca/en"
    COLLECTION_URL = f"{BASE_URL}/collections/frontpage"
    SOURCE_NAME = "Kohi"
    ROASTER_NAME = "Kohi"
    INCLUDE_TAGS = ()
    EXCLUDE_HANDLE_KEYWORDS = (*ShopifyScraper.EXCLUDE_HANDLE_KEYWORDS, "carte", "cadeau", "boite", "trio")
    EXCLUDE_TAGS = ("Cadeau", "Boite", "Trio", "Carte")
    HAS_EXTRANEOUS_TASTING_NOTES_TAG = True


class SubtextScraper(ShopifyScraper):
    """Shopify configuration for Subtext products."""

    # Subtext's collection JSON body is mostly shipping copy. The real coffee
    # specs are rendered on product pages in Shogun rich-text rows, while notes
    # live in the SEO/meta description handled by the shared meta fallback.
    BASE_URL = "https://www.subtext.coffee"
    COLLECTION_URL = f"{BASE_URL}/collections/filter-coffee-beans"
    SOURCE_NAME = "Subtext"
    ROASTER_NAME = "Subtext Coffee"
    INCLUDE_TAGS = ()
    INCLUDE_PRODUCT_TYPES = ("Coffee",)
    HYDRATE_COLLECTION_PRODUCTS = True
    EXCLUDE_HANDLE_KEYWORDS = (*ShopifyScraper.EXCLUDE_HANDLE_KEYWORDS, "sample-box", "test-batch")
    PRODUCT_FACT_SELECTORS = (
        "div.shg-rich-text.shg-default-text-content:has(p:-soup-contains('Region')):has(p:-soup-contains('Process'))",
    )


class ArteryScraper(ShopifyScraper):
    """Shopify configuration for The Artery Community Roasters products."""

    # The by-the-bag collection is already coffee-focused; product types and tags
    # are blank, so rely on the collection path plus shared gift/subscription
    # excludes. Their screen-printed shirt also appears there, so handle-filter it.
    BASE_URL = "https://thearterycommunityroasters.com"
    COLLECTION_URL = f"{BASE_URL}/collections/by-the-bag"
    SOURCE_NAME = "The Artery"
    ROASTER_NAME = "The Artery Community Roasters"
    INCLUDE_TAGS = ()
    EXCLUDE_HANDLE_KEYWORDS = (*ShopifyScraper.EXCLUDE_HANDLE_KEYWORDS, "shirt")


class EthicaScraper(ShopifyScraper):
    """Shopify configuration for Ethica products."""

    BASE_URL = "https://ethicaroasters.com"
    COLLECTION_URL = f"{BASE_URL}/collections/filter-coffee"
    SOURCE_NAME = "Ethica"
    ROASTER_NAME = "Ethica Coffee Roasters"
    INCLUDE_TAGS = ()
    INCLUDE_PRODUCT_TYPES = ("Coffee",)


class RabbitHoleScraper(ShopifyScraper):
    """Shopify configuration for Rabbit Hole products."""

    # Rabbit Hole's all-coffee collection can carry wholesale-only tags, but
    # those products should not enter consumer cart recommendations. Their
    # tasting boxes are coffee-adjacent bundles, not a single orderable bag.
    # A few single origins publish process in the handle/title but not the body,
    # so enable the conservative handle-process fallback for this source.
    BASE_URL = "https://www.rabbitholeroasters.com"
    COLLECTION_URL = f"{BASE_URL}/collections/all-coffee"
    SOURCE_NAME = "Rabbit Hole"
    ROASTER_NAME = "Rabbit Hole Roasters"
    INCLUDE_TAGS = ("All Coffee",)
    INCLUDE_PRODUCT_TYPES = ("Coffee",)
    EXCLUDE_TAGS = ("wholesale-only", "experience boxes")
    EXTRACT_HANDLE_PROCESS_FACTS = True


class EscapeScraper(ShopifyScraper):
    """Shopify configuration for Escape Coffee products."""

    # Escape renders the useful bean specs in the product-page accordion, not in
    # collection JSON. Scope to that accordion so unrelated carousels/nav copy
    # cannot win product facts.
    BASE_URL = "https://escape.cafe"
    COLLECTION_URL = f"{BASE_URL}/collections/coffees"
    SOURCE_NAME = "Escape"
    ROASTER_NAME = "Escape Coffee Roasters"
    INCLUDE_TAGS = ()
    INCLUDE_PRODUCT_TYPES = ("Coffee",)
    SKIP_UNAVAILABLE_PRODUCTS = True
    HYDRATE_COLLECTION_PRODUCTS = True
    PRODUCT_FACT_SELECTORS = ("div#ProductAccordion-beans",)
    TASTING_NOTE_TEXT_SELECTORS = (
        "p.productHero__ingredients",
        *ShopifyScraper.TASTING_NOTE_TEXT_SELECTORS,
    )


class PiratesScraper(ShopifyScraper):
    """Shopify configuration for Pirates of Coffee products."""

    # Pirates keeps rich facts in collection JSON, but the all-coffee collection
    # also carries bundles/matcha and unavailable archive items; keep this source
    # focused on currently orderable coffee beans.
    BASE_URL = "https://piratesofcoffee.com"
    COLLECTION_URL = f"{BASE_URL}/collections/all-coffee"
    SOURCE_NAME = "Pirates"
    ROASTER_NAME = "Pirates of Coffee"
    INCLUDE_TAGS = ()
    INCLUDE_PRODUCT_TYPES = ("Coffee Beans",)
    SKIP_UNAVAILABLE_PRODUCTS = True
    EXCLUDE_HANDLE_KEYWORDS = (
        *ShopifyScraper.EXCLUDE_HANDLE_KEYWORDS,
        "treasure-box",
        "box-set",
        "matcha",
        "drip-bags",
        "cascara",
    )


class Celcius94Scraper(ShopifyScraper):
    """Shopify configuration for 94 Celcius products."""

    # The /cafes collection is the English storefront's coffee boundary; product
    # type filtering catches any stray equipment that appears in broader feeds.
    BASE_URL = "https://94celcius.com/en"
    COLLECTION_URL = f"{BASE_URL}/collections/cafes"
    SOURCE_NAME = "94 Celcius"
    ROASTER_NAME = "94 Celcius"
    INCLUDE_TAGS = ()
    INCLUDE_PRODUCT_TYPES = ("Coffee",)


class CafePistaScraper(ShopifyScraper):
    """Shopify configuration for Cafe Pista products."""

    # Cafe Pista puts visible specs in the product description HTML. Hydrate and
    # scope to the RTE block to avoid unrelated collection/header text.
    BASE_URL = "https://cafepista.com/en"
    COLLECTION_URL = f"{BASE_URL}/collections/sacs"
    SOURCE_NAME = "Cafe Pista"
    ROASTER_NAME = "Cafe Pista"
    INCLUDE_TAGS = ()
    INCLUDE_PRODUCT_TYPES = ("Sac de café",)
    EXCLUDE_TAGS = ("wholesale-only",)
    EXCLUDE_HANDLE_KEYWORDS = (
        *ShopifyScraper.EXCLUDE_HANDLE_KEYWORDS,
        "trio",
        "ensemble",
        "tasting-set",
    )
    HYDRATE_COLLECTION_PRODUCTS = True
    PRODUCT_FACT_SELECTORS = ("rte-formatter.rte",)


class JungleScraper(ShopifyScraper):
    """Shopify configuration for Jungle products."""

    BASE_URL = "https://junglelivraisoncafe.com"
    COLLECTION_URL = f"{BASE_URL}/collections/classics"
    SOURCE_NAME = "Jungle"
    ROASTER_NAME = "Jungle"
    INCLUDE_TAGS = ()
    INCLUDE_PRODUCT_TYPES = ("Café", "Coffee")
    SKIP_UNAVAILABLE_PRODUCTS = True


class NucleusScraper(ShopifyScraper):
    """Shopify configuration for Nucleus products."""

    BASE_URL = "https://nucleuscoffee.com/en"
    COLLECTION_URL = f"{BASE_URL}/collections/lab-cafe"
    SOURCE_NAME = "Nucleus"
    ROASTER_NAME = "Nucleus"
    INCLUDE_TAGS = ()
    INCLUDE_PRODUCT_TYPES = ("Café", "Coffee")
    USE_EXTRA_COFFEE_PRODUCT_DESCRIPTORS = True
    SKIP_UNAVAILABLE_PRODUCTS = True
    # ok so here, the collection JSON returned nothing, so turning that off
    USE_COLLECTION_JSON = False
    # and in the debug file I see "<div class="notes"> \n<span class="note">Pêche sucrée</span> ...", and this is how you get them
    TASTING_NOTE_SELECTORS = ("div.notes span.note",)
    PRODUCT_FACT_SELECTORS = ("div.specs",)

    def _extract_html_product_facts(self, html_soup: BeautifulSoup) -> dict[str, str]:
        facts = super()._extract_html_product_facts(html_soup)
        icon_facts = self._extract_spec_icon_facts(html_soup)
        if icon_facts:
            for field, value in facts.items():
                icon_facts.setdefault(field, value)
            return icon_facts
        return facts

    def _extract_spec_icon_facts(self, html_soup: BeautifulSoup) -> dict[str, str]:
        mapping = {
            "iconoir-ecology-book": "varietal",
            "iconoir-flask": "process",
            "iconoir-globe": "origin",
            "iconoir-upload": "altitude",
        }
        facts: dict[str, str] = {}
        for spec in html_soup.select("div.specs span.spec"):
            icon = spec.select_one("i")
            if icon is None:
                continue
            classes = icon.get("class")
            if isinstance(classes, str):
                classes = classes.split()
            for cls in classes or []:
                field = mapping.get(cls)
                if field is None or field in facts:
                    continue
                text = spec.get_text(" ", strip=True)
                if text:
                    facts[field] = text
                    break
        return facts


class SipstruckScraper(ShopifyScraper):
    """Shopify configuration for Sipstruck products."""

    BASE_URL = "https://sipstruck.com"
    COLLECTION_URL = f"{BASE_URL}/collections/coffee"
    SOURCE_NAME = "Sipstruck"
    ROASTER_NAME = "Sipstruck"
    INCLUDE_TAGS = ()
    INCLUDE_PRODUCT_TYPES = ("Café", "Coffee")
    SKIP_UNAVAILABLE_PRODUCTS = True


class ZaAndKloScraper(ShopifyScraper):
    """Shopify configuration for Za & Klo products."""

    # Their visible /collections/coffees URL does not expose collection JSON, but
    # the product index does. Product type plus bundle handles keep it coffee-only.
    BASE_URL = "https://zaandklo.com"
    COLLECTION_URL = f"{BASE_URL}/products"
    SOURCE_NAME = "Za & Klo"
    ROASTER_NAME = "Za & Klo"
    INCLUDE_TAGS = ()
    INCLUDE_PRODUCT_TYPES = ("coffee", "Coffee")
    SKIP_UNAVAILABLE_PRODUCTS = True
    EXCLUDE_HANDLE_KEYWORDS = (
        *ShopifyScraper.EXCLUDE_HANDLE_KEYWORDS,
        "discovery-box",
        "roaster-box",
        "roasters-box",
    )


class NektarScraper(ShopifyScraper):
    """Shopify configuration for Nektar products."""

    # Nektar's coffee collection includes discovery bundles. The coffee bags
    # themselves expose rich facts in collection JSON using "Taste notes".
    BASE_URL = "https://nektar.ca/en"
    COLLECTION_URL = f"{BASE_URL}/collections/tous-les-cafes"
    SOURCE_NAME = "Nektar"
    ROASTER_NAME = "Nektar Cafeologue"
    INCLUDE_TAGS = ()
    INCLUDE_PRODUCT_TYPES = ("Cafés",)
    EXCLUDE_HANDLE_KEYWORDS = (
        *ShopifyScraper.EXCLUDE_HANDLE_KEYWORDS,
        "trio",
        "ensemble",
        "decouverte",
        "bundle",
    )


class SeptemberScraper(ShopifyScraper):
    """Shopify configuration for September Coffee products."""

    # September's collection JSON has empty descriptions. Product pages expose
    # a structured parameter list plus an "In the cup" paragraph, so hydrate.
    BASE_URL = "https://september.coffee"
    COLLECTION_URL = f"{BASE_URL}/collections/coffee"
    SOURCE_NAME = "September"
    ROASTER_NAME = "September Coffee"
    INCLUDE_TAGS = ()
    INCLUDE_PRODUCT_TYPES = ("Coffee",)
    SKIP_UNAVAILABLE_PRODUCTS = True
    HYDRATE_COLLECTION_PRODUCTS = True
    PRODUCT_FACT_SELECTORS = ("ul.parameter-list",)
    TASTING_NOTE_TEXT_SELECTORS = (
        "div.product-info-block:has(h2:-soup-contains('In the cup')) p",
        *ShopifyScraper.TASTING_NOTE_TEXT_SELECTORS,
    )


class MonogramScraper(ShopifyScraper):
    """Shopify configuration for Monogram products."""

    # Monogram's coffee collection JSON is available at /all-coffees. Hydrate so
    # the product text block can provide origin/process/notes consistently, and
    # stop before cross-links such as "Want this for espresso?".
    BASE_URL = "https://monogramcoffee.com"
    COLLECTION_URL = f"{BASE_URL}/collections/all-coffees"
    SOURCE_NAME = "Monogram"
    ROASTER_NAME = "Monogram Coffee"
    INCLUDE_TAGS = ()
    INCLUDE_PRODUCT_TYPES = ("Whole Bean",)
    SKIP_UNAVAILABLE_PRODUCTS = True
    HYDRATE_COLLECTION_PRODUCTS = True
    PRODUCT_FACT_STOP_LABELS = (
        *DEFAULT_PRODUCT_FACT_STOP_LABELS,
        "Want this for espresso",
        "Want this for filter",
    )
    PRODUCT_FACT_SELECTORS = ("div.product__text.rte",)


class NarvalScraper(ShopifyScraper):
    """Shopify configuration for Narval products."""

    # The 340g collection avoids bundles and 1.5kg duplicates. Shopify reports
    # zero variant grams, so the shared leading-description weight fallback reads
    # the visible "340g" line where present.
    BASE_URL = "https://narval.cafe/en"
    COLLECTION_URL = f"{BASE_URL}/collections/340g"
    SOURCE_NAME = "Narval"
    ROASTER_NAME = "Narval"
    INCLUDE_TAGS = ()
    INCLUDE_PRODUCT_TYPES = ("Coffee",)
    EXCLUDE_HANDLE_KEYWORDS = (*ShopifyScraper.EXCLUDE_HANDLE_KEYWORDS, "coffret", "mug")
