"""Shopify-oriented scraping and adapters for several supported roasters.

The generic ``ShopifyScraper`` prefers Shopify collection JSON because several
storefront collection pages currently trigger Cloudflare challenges. A source
can still opt out when product pages are required for reliable metadata.
"""

from __future__ import annotations

import re
from typing import Any, cast
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from gesha.coffee_data import CoffeeData, CoffeeVariantData
from gesha.measurements import is_retail_variant, parse_weight_grams, weight_to_grams
from gesha.normalization import normalize_search_text, normalize_tasting_notes
from gesha.parsers.common import (
    DEFAULT_PRODUCT_FACT_LABELS,
    DEFAULT_PRODUCT_FACT_STOP_LABELS,
    extract_labeled_product_facts_from_html,
    extract_labeled_product_facts_from_text,
)
from gesha.scrapers.base_scraper import BaseScraper


def _first_non_blank(*values: str | None) -> str | None:
    """Return the first source value that carries actual content."""
    # Product-page facts, JSON facts, and title facts are passed in precedence order.
    for value in values:
        if value:
            cleaned = value.strip()
            if cleaned:
                return cleaned
    return None


class ShopifyScraper(BaseScraper):
    """Extract coffee products from stores exposing Shopify product JSON."""

    # Collection JSON avoids the collection-page Cloudflare challenge for most
    # stores. Source configs can opt out if collection JSON is too incomplete.
    USE_COLLECTION_JSON: bool = True

    # Shopify limits collection JSON pages, so large/archive-heavy stores are
    # paginated until a short or empty page proves the collection is exhausted.
    PRODUCTS_JSON_LIMIT = 250

    # Product links may be plain ``/products/x`` or collection-scoped
    # ``/collections/coffee/products/x`` links.
    PRODUCT_URL_PATTERN = re.compile(r"^/(?:[^/]+/)?(?:collections/[^/]+/)?products/[^/?#]+$")
    PRODUCT_LINK_ATTRIBUTES: tuple[str, ...] = ("href", "data-url")

    # Stores with reliable tags can require coffee tags; stores without them
    # opt out by setting INCLUDE_TAGS to an empty tuple. Product-type filters
    # cover stores that expose "Coffee", "Whole Bean", or translated type names.
    INCLUDE_TAGS: tuple[str, ...] = ("coffee",)
    INCLUDE_PRODUCT_TYPES: tuple[str, ...] = ()
    EXCLUDE_HANDLE_KEYWORDS: tuple[str, ...] = ("subscription", "sub", "gift", "recurring")
    EXCLUDE_TAGS: tuple[str, ...] = ()
    EXCLUDE_PRODUCT_TYPES: tuple[str, ...] = ()
    SKIP_UNAVAILABLE_PRODUCTS = False
    HYDRATE_COLLECTION_PRODUCTS = False
    USE_EXTRA_COFFEE_PRODUCT_DESCRIPTORS = False

    # Shared label dictionaries can be extended or narrowed per roaster.
    PRODUCT_FACT_LABELS = DEFAULT_PRODUCT_FACT_LABELS
    PRODUCT_FACT_STOP_LABELS = DEFAULT_PRODUCT_FACT_STOP_LABELS
    PRODUCT_FACT_SELECTORS: tuple[str, ...] = ()

    # Some storefronts keep notes outside labeled description copy. Use
    # TASTING_NOTE_SELECTORS when each matched element is one note, and
    # TASTING_NOTE_TEXT_SELECTORS when a matched block contains a comma/sentence
    # separated note string. The caption selector is a common Shopify theme
    # pattern, so keep it on the shared path instead of hard-coding a fallback.
    TASTING_NOTE_SELECTORS: tuple[str, ...] = ()
    TASTING_NOTE_TEXT_SELECTORS: tuple[str, ...] = ("p.product__text.inline-richtext.caption-with-letter-spacing",)
    HAS_EXTRANEOUS_TASTING_NOTES_TAG = False

    # Dash-separated title facts are source-specific and stay opt-in because
    # ``Origin - Name`` and ``Name - Process`` can otherwise look identical.
    EXTRACT_DASH_TITLE_FACTS = False

    # Handle-derived process facts are also opt-in: product handles are stable,
    # but words like "honey" can be either a process or a flavor note.
    EXTRACT_HANDLE_PROCESS_FACTS = False
    HANDLE_PROCESS_FACTS: tuple[tuple[str, str], ...] = (
        ("anaerobic-natural", "anaerobic natural"),
        ("anaerobic-washed", "anaerobic washed"),
        ("semi-washed", "semi-washed"),
        ("wet-hulled", "wet hulled"),
        ("washed", "washed"),
        ("natural", "natural"),
        ("honey", "honey"),
    )

    NOTE_HINT_SEPARATORS = ("|", ",", ";", "+", " x ", "·", "•", "Â", "â")
    BULLET_NOTE_SEPARATORS = ("·", "•", "Â", "â")
    ROAST_SCALE_PATTERN = re.compile(r"\blight\b.*\bdark\b|[●○]", re.IGNORECASE)
    META_TASTING_NOTES_PATTERN = re.compile(r"\btasting\s+notes?\s+of\s+(.+?)(?:[.!?]|$)", re.IGNORECASE)

    def extract_product_urls(self, html: str) -> list[str]:
        """Convert collection product links into canonical Shopify product URLs."""
        # This is the old/product-page path: start from collection HTML and then
        # visit each discovered product URL.
        soup = BeautifulSoup(html, "html.parser")
        urls: list[str] = []

        # Shopify themes expose product targets in anchors and data attributes.
        for element in soup.select("a[href*='/products/'], [data-url*='/products/']"):
            for attribute in self.PRODUCT_LINK_ATTRIBUTES:
                raw_href = element.get(attribute)
                if not isinstance(raw_href, str):
                    continue
                href = raw_href.split("?", 1)[0].strip()
                path = urlparse(href).path if href.startswith(("http://", "https://")) else href
                if not self.PRODUCT_URL_PATTERN.match(path):
                    continue

                handle = path.rstrip("/").rsplit("/", 1)[-1].lower()
                if self._is_excluded_handle(handle):
                    continue

                # Canonicalize collection links before de-duping at the end.
                urls.append(self._canonical_product_url(urljoin(self.BASE_URL, href)))
        return sorted(dict.fromkeys(urls))

    def scrape(self) -> list[CoffeeData]:
        """Prefer collection JSON, unless a source explicitly opts out."""
        # The JSON feed can give title, tags, description, and variants in one
        # request. Opted-out sources use BaseScraper's product-page workflow.
        if self.USE_COLLECTION_JSON:
            coffees = self._scrape_collection_json()
            if coffees is not None:
                return coffees
        return super().scrape()

    def _storefront_origin(self) -> str:
        """Return the scheme/host portion that owns Shopify product paths."""
        # BASE_URL may include a locale path for future sources, but absolute
        # Shopify product/cart paths are rooted at the storefront origin.
        parsed = urlparse(self.BASE_URL)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _product_path_prefix(self) -> str:
        """Return any locale prefix that should precede ``/products/<handle>``."""
        # Locale-aware stores expose paths such as /en/collections/coffee and
        # /en/products/foo. The product prefix is the path segment before the
        # Shopify collection/products namespace.
        path = urlparse(self.COLLECTION_URL).path.rstrip("/")
        segments = [segment for segment in path.split("/") if segment]
        if not segments:
            return ""

        if "collections" in segments:
            prefix_segments = segments[: segments.index("collections")]
        elif segments[-1] == "products":
            prefix_segments = segments[:-1]
        else:
            prefix_segments = segments
        return f"/{'/'.join(prefix_segments)}" if prefix_segments else ""

    def _collection_products_json_url(self, page: int = 1) -> str:
        """Build Shopify's public collection products JSON endpoint."""
        # Preserve the configured collection/locale path so each roaster can
        # choose ``/en``, ``/collections/coffee``, or Shopify's product index.
        parsed = urlparse(self.COLLECTION_URL)
        path = parsed.path.rstrip("/")
        origin = f"{parsed.scheme}://{parsed.netloc}"

        if path.endswith("/products"):
            json_path = f"{path}.json"
        elif path:
            json_path = f"{path}/products.json"
        else:
            json_path = "/products.json"
        return f"{origin}{json_path}?limit={self.PRODUCTS_JSON_LIMIT}&page={page}"

    def _scrape_collection_json(self) -> list[CoffeeData] | None:
        """Fetch every Shopify collection JSON page when the feed is available."""
        coffees: list[CoffeeData] = []
        page = 1
        while True:
            collection_json_url = self._collection_products_json_url(page=page)
            response = self.session.get(collection_json_url, timeout=15)

            # A first-page 404 means the store/theme does not expose this endpoint;
            # allow the caller to fall back to the older product-page path.
            if response.status_code == 404 and page == 1:
                return None

            # Any other HTTP failure makes the refresh unsafe: a partial catalog
            # could delete valid cached rows, so return an empty failed scrape.
            if response.status_code >= 400:
                self._log_http_failure("fetch Shopify collection JSON", collection_json_url, response)
                return []
            response.raise_for_status()

            try:
                # Some storefronts may return HTML from this URL; that is not usable
                # as a Shopify collection feed.
                payload = response.json()
            except ValueError:
                return None if page == 1 else []
            if not isinstance(payload, dict):
                return None if page == 1 else []

            products = payload.get("products")
            if not isinstance(products, list):
                return None if page == 1 else []
            if not products:
                break

            for raw_product in products:
                # Collection JSON is external data, so validate shape before casting.
                if not isinstance(raw_product, dict):
                    continue

                product_data = self._product_from_collection_json(cast(dict[str, Any], raw_product))
                if not self._is_coffee_product(product_data):
                    continue
                if self.SKIP_UNAVAILABLE_PRODUCTS and not self._is_available_product(product_data):
                    continue

                # Shopify handles are enough to build canonical product URLs.
                handle = str(product_data.get("handle") or "").strip()
                if not handle:
                    continue

                url = self._canonical_product_url(urljoin(self.BASE_URL, f"/products/{handle}"))
                html_soup: BeautifulSoup | None = None
                html_facts: dict[str, str] | None = None
                if self.HYDRATE_COLLECTION_PRODUCTS:
                    html_soup, html_facts = self._product_page_html_facts(url)
                coffees.append(self._coffee_from_product(product_data, url, html_soup=html_soup, html_facts=html_facts))

            if len(products) < self.PRODUCTS_JSON_LIMIT:
                break
            page += 1
        return coffees

    def _product_from_collection_json(self, product_data: dict[str, Any]) -> dict[str, Any]:
        """Normalize collection-feed product JSON to the product-page JSON shape."""
        # Copy before adapting so tests and callers can reuse their raw fixture.
        product = dict(product_data)

        # Collection JSON calls this field ``body_html``; product ``.js`` calls
        # the equivalent field ``description``.
        if "description" not in product and "body_html" in product:
            product["description"] = product["body_html"]

        # Product type is named differently across Shopify endpoints.
        if "type" not in product and "product_type" in product:
            product["type"] = product["product_type"]

        # Collection feeds can omit product-level availability, so infer it from
        # variants when possible.
        if "available" not in product:
            variants = self._raw_variants(product)
            product["available"] = (
                any(bool(variant.get("available", True)) for variant in variants) if variants else True
            )

        # Collection variant prices are usually decimal dollars; normalize to
        # integer cents so the rest of the parser sees one shape.
        if "price" not in product:
            product["price"] = self._first_variant_price_cents(product)
        return product

    def scrape_product(self, url: str) -> CoffeeData | None:
        """Fetch Shopify HTML first, then JSON support data for one product."""
        html_soup, html_facts = self._product_page_html_facts(url)

        # Shopify JSON is still the reliable source for title, variants, price, availability, tags, and description fallbacks.
        session = cast(Any, self.session)
        headers = session.headers.copy()
        headers["Referer"] = url
        response = session.get(f"{url}.js", headers=headers, timeout=15)
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            self._log_http_failure("fetch product JSON", f"{url}.js", response)
            return None
        response.raise_for_status()
        product_data = cast(dict[str, Any], response.json())

        if not self._is_coffee_product(product_data):
            return None

        # Merge the page facts and Shopify payload into the normalized DTO.
        return self._coffee_from_product(product_data, url, html_soup=html_soup, html_facts=html_facts)

    def _product_page_html_facts(self, url: str) -> tuple[BeautifulSoup | None, dict[str, str]]:
        """Fetch product-page HTML facts for sources that need richer metadata."""
        # Product-page HTML usually carries the richest label/value metadata, but
        # collection JSON remains the cheaper default for batch-friendly sources.
        html_soup: BeautifulSoup | None = None
        html_facts: dict[str, str] = {}
        res_html = self.session.get(url, timeout=15)
        if res_html.status_code == 200:
            html_soup = BeautifulSoup(res_html.text, "html.parser")
            html_facts = self._extract_html_product_facts(html_soup)
        elif res_html.status_code >= 400:
            self._log_http_failure("fetch product HTML", url, res_html)
        return html_soup, html_facts

    def parse_product(self, html: str, url: str) -> CoffeeData:
        """Prevent the base HTML parser path for JSON-driven Shopify products."""
        # Shopify product HTML is not parsed directly; ``scrape_product`` pairs
        # HTML facts with the product ``.js`` payload.
        raise NotImplementedError("ShopifyScraper parses product JSON instead of product HTML.")

    def _canonical_product_url(self, url: str) -> str:
        """Strip collection prefixes so one Shopify item has one stored URL."""
        # The final path component is the product handle in both URL shapes.
        # Locale prefixes come from COLLECTION_URL so /en stores stay on /en.
        parsed = urlparse(url)
        handle = parsed.path.rstrip("/").rsplit("/", 1)[-1]
        return f"{self._storefront_origin()}{self._product_path_prefix()}/products/{handle}"

    def _normalized_config_values(self, values: tuple[str, ...]) -> set[str]:
        """Normalize source config text before comparing tags and type labels."""
        # Product types and tags can differ by case, punctuation, or accents
        # across locale-aware storefronts, so share the search-text normalizer.
        return {value for raw_value in values if (value := normalize_search_text(raw_value))}

    def _product_type(self, product_data: dict[str, Any]) -> str:
        """Return the normalized Shopify product type for filter checks."""
        raw_type = product_data.get("type") or product_data.get("product_type") or ""
        return normalize_search_text(str(raw_type)) or ""

    def _normalize_tags(self, product_data: dict[str, Any]) -> set[str]:
        """Return lowercase Shopify tags independent of API string/list shape."""
        # Product ``.js`` and collection feeds can expose tags as CSV text or a list.
        raw_tags = product_data.get("tags") or []
        if isinstance(raw_tags, str):
            raw_tags = [tag.strip() for tag in raw_tags.split(",") if tag.strip()]
        return {tag for raw_tag in raw_tags if (tag := normalize_search_text(str(raw_tag)))}

    def _is_excluded_handle(self, handle: str) -> bool:
        """Return whether a product handle belongs to a non-catalog item."""
        # Handles tend to be stable even when product copy changes.
        return any(keyword in handle for keyword in self.EXCLUDE_HANDLE_KEYWORDS)

    def _is_coffee_product(self, product_data: dict[str, Any]) -> bool:
        """Reject subscriptions and accept products satisfying source tag rules."""
        handle = str(product_data.get("handle") or "").lower()
        tags = self._normalize_tags(product_data)
        product_type = self._product_type(product_data)
        include_tags = self._normalized_config_values(self.INCLUDE_TAGS)
        include_types = self._normalized_config_values(self.INCLUDE_PRODUCT_TYPES)
        exclude_tags = self._normalized_config_values(self.EXCLUDE_TAGS)
        exclude_types = self._normalized_config_values(self.EXCLUDE_PRODUCT_TYPES)

        # Excluded handles/tags catch subscription, gift, and kit-like products.
        if (
            self._is_excluded_handle(handle)
            or bool(tags.intersection(exclude_tags))
            or (product_type in exclude_types)
            or any(keyword in tags for keyword in self.EXCLUDE_HANDLE_KEYWORDS)
        ):
            return False

        # Some roasters tag coffee reliably; others need product type filters.
        if include_tags or include_types:
            if bool(tags.intersection(include_tags) or product_type in include_types):
                return True

            # A few storefronts publish coffee products without a clear explicit
            # coffee type, but their collection tags still signal the catalog intent.
            if self.USE_EXTRA_COFFEE_PRODUCT_DESCRIPTORS and tags.intersection({"lab", "filtre", "espresso"}):
                return True
            return False

        return True

    def _is_available_product(self, product_data: dict[str, Any]) -> bool:
        """Return whether the Shopify product has at least one available variant."""
        # Collection feeds can omit product-level availability; variant data is
        # the source of truth for cart-usable availability when present.
        variants = self._raw_variants(product_data)
        if variants:
            return any(bool(variant.get("available", True)) for variant in variants)
        return bool(product_data.get("available", True))

    def _coffee_from_product(
        self,
        product_data: dict[str, Any],
        url: str,
        html_soup: BeautifulSoup | None = None,
        html_facts: dict[str, str] | None = None,
    ) -> CoffeeData:
        """Merge product-page facts, Shopify JSON, and title fallbacks."""
        # Extract every source of structured facts before choosing precedence.
        description = self._description_text(product_data)
        json_facts = self._extract_json_product_facts(product_data, description)
        page_facts = html_facts or (self._extract_html_product_facts(html_soup) if html_soup else {})
        title = normalize_search_text(str(product_data.get("title") or "Unknown coffee")) or "unknown coffee"
        title_facts = self._extract_details_from_title(title)
        handle_process = self._extract_process_from_handle(product_data, url)

        # Prefer explicit page labels, then Shopify description labels, then
        # title/handle heuristics only for fields those sources express safely.
        origin = _first_non_blank(page_facts.get("origin"), json_facts.get("origin"), title_facts.get("origin"))
        # Some roasters like to put some novels in the origin field, so truncate to a reasonable number of words
        if origin and len(origin) > 100:
            words = origin.split()
            origin = " ".join(words[:5])

        producer = _first_non_blank(page_facts.get("producer"), json_facts.get("producer"))
        process = _first_non_blank(
            page_facts.get("process"),
            json_facts.get("process"),
            title_facts.get("process"),
            handle_process,
        )
        varietal = _first_non_blank(page_facts.get("varietal"), json_facts.get("varietal"))
        altitude = _first_non_blank(page_facts.get("altitude"), json_facts.get("altitude"))
        roast_style = _first_non_blank(
            page_facts.get("roast_style"),
            json_facts.get("roast_style"),
            self._extract_roast_style(product_data),
        )
        bag_size = _first_non_blank(
            page_facts.get("bag_size"),
            json_facts.get("bag_size"),
            self._extract_bag_size(product_data),
            self._extract_bag_size_from_description(description),
        )
        tasting_notes = self._extract_tasting_notes(
            description,
            html_soup=html_soup,
            page_facts=page_facts,
            json_facts=json_facts,
        )

        # Variants are parsed before choosing display price/size because the
        # smallest available retail bag is the canonical cart choice.
        variants = self._extract_variants(product_data)
        default_variant = self._smallest_available_variant(variants)

        # Normalize at the boundary so database and display layers stay simple.
        return CoffeeData(
            roaster=self.ROASTER_NAME,
            name=title,
            origin=normalize_search_text(origin),
            producer=producer,
            process=normalize_search_text(process),
            varietal=varietal,
            altitude=altitude,
            tasting_notes=tasting_notes,
            roast_style=roast_style,
            price_cents=default_variant.price_cents if default_variant else self._extract_price(product_data),
            bag_size=_first_non_blank(default_variant.bag_size, bag_size) if default_variant else bag_size,
            url=url,
            availability=default_variant.availability if default_variant else bool(product_data.get("available", True)),
            variants=variants,
        )

    def _description_text(self, product_data: dict[str, Any]) -> str:
        """Flatten Shopify's HTML description into label-searchable text."""
        # Newlines preserve paragraph/list boundaries for loose note fallbacks.
        html = str(product_data.get("description") or "")
        return BeautifulSoup(html, "html.parser").get_text("\n", strip=True)

    def _extract_details(self, description: str) -> dict[str, str]:
        """Extract labeled metadata exposed in Shopify descriptions."""
        # This handles the text form of product facts after HTML tags are removed.
        return extract_labeled_product_facts_from_text(
            description,
            label_aliases=self.PRODUCT_FACT_LABELS,
            stop_labels=self.PRODUCT_FACT_STOP_LABELS,
        )

    def _extract_json_product_facts(self, product_data: dict[str, Any], description: str) -> dict[str, str]:
        """Extract product facts from Shopify JSON description fields."""
        raw_html = str(product_data.get("description") or "")
        if raw_html.strip():
            raw_soup = BeautifulSoup(raw_html, "html.parser")

            # JSON descriptions can contain the same theme-specific fact blocks as product pages, so selector configs should scope both paths.
            if selected_facts := self._extract_selected_html_product_facts(raw_soup):
                return selected_facts

            # Row-aware HTML parsing keeps labels scoped to their paragraph/list
            # item, which avoids swallowing trailing marketing copy as a fact.
            html_facts = extract_labeled_product_facts_from_html(
                raw_soup,
                label_aliases=self.PRODUCT_FACT_LABELS,
                stop_labels=self.PRODUCT_FACT_STOP_LABELS,
            )
            if html_facts:
                return html_facts

        # Plain-text parsing remains the fallback for sparse/non-HTML payloads.
        return self._extract_details(description)

    def _extract_selected_html_product_facts(self, html_soup: BeautifulSoup) -> dict[str, str]:
        """Read labeled facts from configured HTML blocks only."""
        selected_facts: dict[str, str] = {}

        # NOW HERE WITH NUCLEUS -- NEED TO SET PRODUCT FACT SELECTORS TO SOMETHING (I THINK)
        # Source configs can point directly at known metadata blocks. This is safer than page-wide parsing for themes with long story sections.
        for selector in self.PRODUCT_FACT_SELECTORS:
            blocks = html_soup.select(selector)

            # Themes sometimes nest the compact spec sheet inside a broader story wrapper that also matches the selector.
            # Parse deepest blocks first so specific facts win, then let ancestors fill missing fields.
            blocks.sort(key=lambda block: len(list(block.parents)), reverse=True)
            for block in blocks:
                block_facts = extract_labeled_product_facts_from_html(
                    block,
                    label_aliases=self.PRODUCT_FACT_LABELS,
                    stop_labels=self.PRODUCT_FACT_STOP_LABELS,
                )
                for key, value in block_facts.items():
                    selected_facts.setdefault(key, value)
        return selected_facts

    def _extract_html_product_facts(self, html_soup: BeautifulSoup) -> dict[str, str]:
        """Read product-page label/value sections before JSON fallbacks."""

        if selected_facts := self._extract_selected_html_product_facts(html_soup):
            return selected_facts

        # If no selector is configured or populated, scan the whole product page.
        return extract_labeled_product_facts_from_html(
            html_soup,
            label_aliases=self.PRODUCT_FACT_LABELS,
            stop_labels=self.PRODUCT_FACT_STOP_LABELS,
        )

    def _extract_details_from_title(self, title: str) -> dict[str, str | None]:
        """Try to extract origin and process from ``Origin - Name | Process`` titles."""
        details: dict[str, str | None] = {"origin": None, "process": None}

        # Pipe-separated titles usually put process on the far right.
        if "|" in title:
            pipe_parts = [part.strip() for part in title.split("|")]
            details["origin"] = pipe_parts[0]
            if len(pipe_parts) >= 2:
                details["process"] = pipe_parts[-1]

        # Pipe-separated origins may still include a dash-separated coffee name.
        dash_pattern = r"\s*[-\u2012\u2013\u2014\u2212]\s*"
        if details["origin"]:
            dash_parts = re.split(dash_pattern, details["origin"])
            if dash_parts:
                details["origin"] = dash_parts[0]

        elif self.EXTRACT_DASH_TITLE_FACTS:
            # Dash-only titles are ambiguous, so sources opt in after fixtures
            # prove they consistently use ``Origin - Name - Process``.
            dash_parts = re.split(dash_pattern, title)
            if len(dash_parts) >= 2:
                details["origin"] = dash_parts[0]
                if len(dash_parts) >= 3:
                    details["process"] = dash_parts[-1]

        return details

    def _extract_process_from_handle(self, product_data: dict[str, Any], url: str) -> str | None:
        """Use opt-in Shopify handles as a final process fallback."""
        if not self.EXTRACT_HANDLE_PROCESS_FACTS:
            return None

        raw_handle = str(product_data.get("handle") or "").strip()
        handle = raw_handle or urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
        normalized_handle = re.sub(r"[^a-z0-9]+", "-", handle.lower()).strip("-")

        # Match whole handle tokens so "washed" works in
        # "ixhuatlan-mexico-washed" but not inside an unrelated word.
        for slug, process in self.HANDLE_PROCESS_FACTS:
            if re.search(rf"(?:^|-){re.escape(slug)}(?:-|$)", normalized_handle):
                return process
        return None

    def _extract_tasting_notes(
        self,
        description: str,
        html_soup: BeautifulSoup | None = None,
        page_facts: dict[str, str] | None = None,
        json_facts: dict[str, str] | None = None,
    ) -> list[str]:
        """Extract source-ordered notes from labeled facts before loose fallbacks."""
        # Labeled product-page facts are the highest-confidence notes source.
        if not self.HAS_EXTRANEOUS_TASTING_NOTES_TAG:
            if page_facts and page_facts.get("tasting_notes"):
                notes = normalize_tasting_notes(page_facts["tasting_notes"])
                if notes:
                    return notes

            # Shopify descriptions often repeat the same labels without page markup.
            facts = json_facts if json_facts is not None else self._extract_details(description)
            value = facts.get("tasting_notes")
            if value:
                notes = normalize_tasting_notes(value)
                if notes:
                    return notes

        # Some themes expose flavor notes outside the product description.
        if html_soup:
            if selected_notes := self._extract_tasting_notes_from_selectors(html_soup):
                filtered_notes = [
                    note for note in selected_notes if note.casefold() not in {"espresso", "pourover", "filter"}
                ]
                return filtered_notes

            if meta_notes := self._extract_tasting_notes_from_meta(html_soup):
                return meta_notes

        # Last chance: only accept very short note-like leading text.
        lines = [line.strip() for line in description.splitlines() if line.strip()]
        if lines:
            first_line = lines[0]
            if first_line.casefold() == "in the cup":
                # Some themes render "In the cup" as a heading followed by one short note per line.
                # Stop before the first prose paragraph or technical table heading.
                note_lines: list[str] = []
                for line in lines[1:]:
                    if len(line) > 50 or line.casefold() in {"technical sheet", "details"}:
                        break
                    note_lines.append(line)
                    if len(note_lines) >= 8:
                        break
                notes = normalize_tasting_notes(note_lines)
                if notes:
                    return notes

            if len(first_line) < 100 and any(separator in first_line for separator in self.NOTE_HINT_SEPARATORS):
                return normalize_tasting_notes(first_line)

            # Some themes put notes in compact leading lines before a roast scale or marketing description.
            # Stop as soon as the text no longer looks like a short note list.
            note_lines: list[str] = []
            for index, line in enumerate(lines):
                if line.lower().__contains__("tasting notes") or line.lower().__contains__("notes de dégustation"):
                    next_line = lines[index + 1] if index + 1 < len(lines) else ""
                    if next_line:
                        notes = normalize_tasting_notes(next_line)
                        if notes:
                            return notes

                # TODO: these are all super weird, are any of them actually useful?
                if line.lower() == "light" or self.ROAST_SCALE_PATTERN.search(line):
                    break
                if len(line) > 60:
                    break
                note_lines.append(line)
                if len(note_lines) >= 7:
                    break

            # Bullet-like separators make this fallback safer than treating any short prose as tasting notes.
            combined_notes = " ".join(note_lines)
            if len(combined_notes) < 140 and any(
                separator in combined_notes for separator in self.BULLET_NOTE_SEPARATORS
            ):
                return normalize_tasting_notes(combined_notes)

        return []

    def _extract_tasting_notes_from_selectors(self, html_soup: BeautifulSoup) -> list[str]:
        """Extract source-ordered notes from configured product-page selectors."""
        selected_notes: list[str] = []

        # Element selectors are for markup like <li>Peach</li>, where each matched node is already one note.
        self._append_unique_notes_from_selectors(
            html_soup,
            self.TASTING_NOTE_SELECTORS,
            selected_notes,
        )

        # Text selectors are for markup like a short description span, where one matched node contains a comma/sentence-separated note string.
        self._append_unique_notes_from_selectors(
            html_soup,
            self.TASTING_NOTE_TEXT_SELECTORS,
            selected_notes,
        )
        return selected_notes

    def _extract_tasting_notes_from_meta(self, html_soup: BeautifulSoup) -> list[str]:
        """Read narrow SEO/meta note phrases when themes hide notes there."""
        # Subtext writes notes as "tasting notes of ..." in page descriptions,
        # while its Shopify JSON body contains only shipping text. Keep the
        # regex phrase-specific so broad marketing copy is not treated as notes.
        for selector in ("meta[name='description']", "meta[property='og:description']"):
            element = html_soup.select_one(selector)
            if element is None:
                continue

            content = element.get("content")
            if not isinstance(content, str):
                continue

            match = self.META_TASTING_NOTES_PATTERN.search(content)
            if not match:
                continue

            notes = normalize_tasting_notes(match.group(1))
            if notes:
                return notes
        return []

    def _append_unique_notes_from_selectors(
        self,
        html_soup: BeautifulSoup,
        selectors: tuple[str, ...],
        selected_notes: list[str],
    ) -> None:
        """Append normalized notes from selector matches without duplicates."""
        for selector in selectors:
            # Selector order is source order, which usually matches the roaster's
            # displayed tasting-note order on the product page.
            for element in html_soup.select(selector):
                for note in normalize_tasting_notes(element.get_text(" ", strip=True)):
                    # Repeated mobile/desktop blocks should not duplicate notes
                    # in the cached catalog.
                    if note not in selected_notes:
                        selected_notes.append(note)

    def _extract_roast_style(self, product_data: dict[str, Any]) -> str | None:
        """Use standard Shopify tags as a fallback roast-style classification."""
        tags = self._normalize_tags(product_data)
        styles = [style for style in ("filter", "espresso") if style in tags]
        return ", ".join(styles) if styles else None

    def _extract_price(self, product_data: dict[str, Any]) -> int | None:
        """Read Shopify's integer-cent product price when it is supplied."""
        # Product-level price is a fallback when variant-specific prices are absent.
        return self._price_cents(product_data.get("price"))

    def _price_cents(self, value: object) -> int | None:
        """Normalize Shopify ``.js`` cent prices and collection dollar prices."""
        # Product ``.js`` usually uses integer cents.
        if isinstance(value, int):
            return value

        # Collection feeds can expose decimal dollar values.
        if isinstance(value, float):
            return round(value * 100)
        if isinstance(value, str):
            stripped = value.strip().replace(",", "")
            if not stripped:
                return None

            # All digits means cents, matching Shopify product ``.js`` shape.
            if re.fullmatch(r"\d+", stripped):
                return int(stripped)

            # Decimal strings mean dollars, matching collection JSON feeds.
            if re.fullmatch(r"\d+(?:\.\d{1,2})?", stripped):
                return round(float(stripped) * 100)
        return None

    def _first_variant_price_cents(self, product_data: dict[str, Any]) -> int | None:
        """Use the first available variant price as a product-level fallback."""
        variants = self._raw_variants(product_data)

        # Prefer available variants so sold-out sizes do not set the display price.
        ordered_variants = sorted(variants, key=lambda variant: not bool(variant.get("available", True)))
        for variant in ordered_variants:
            price = self._price_cents(variant.get("price"))
            if price is not None:
                return price
        return None

    def _raw_variants(self, product_data: dict[str, Any]) -> list[dict[str, object]]:
        """Return dictionary-shaped Shopify variants from an untyped payload."""
        # Shopify stores variant metadata as an untyped list in product JSON.
        raw_variants: object = product_data.get("variants")
        if not isinstance(raw_variants, list):
            return []

        variants: list[dict[str, object]] = []
        for raw_variant in cast(list[object], raw_variants):
            if isinstance(raw_variant, dict):
                variants.append(cast(dict[str, object], raw_variant))
        return variants

    def _variant_weight_grams(self, variant: dict[str, object]) -> int | None:
        """Read reliable weight fields before falling back to variant labels."""
        # Collection feeds often include exact grams directly.
        grams = variant.get("grams")
        if isinstance(grams, int | float) and grams > 0:
            return round(float(grams))

        # Product ``.js`` often exposes weight plus a unit.
        weight = variant.get("weight")
        unit = variant.get("weight_unit")
        if isinstance(weight, int | float) and isinstance(unit, str):
            converted = weight_to_grams(weight, unit)
            if converted is not None:
                return converted
        if isinstance(weight, int | float) and weight > 0:
            # Some product ``.js`` payloads omit ``weight_unit`` but still store
            # the variant weight in grams, as Shopify's storefront JSON commonly does.
            return round(float(weight))

        # Variant labels are the final fallback, e.g. "300g" or "2lb".
        for field in ("title", "public_title", "option1", "sku", "name"):
            raw_value = variant.get(field)
            if isinstance(raw_value, str):
                parsed = parse_weight_grams(raw_value)
                if parsed is not None:
                    return parsed
        return None

    def _variant_bag_size(self, variant: dict[str, object], weight_grams: int | None) -> str | None:
        """Preserve a source bag label, or synthesize one from gram weight."""
        # Prefer the storefront's visible size label when it is present.
        for field in ("title", "public_title", "option1", "sku", "name"):
            raw_value = variant.get(field)
            if isinstance(raw_value, str):
                match = re.search(r"\b\d+(?:\.\d+)?\s*(?:g|kg|oz|lbs?)\b", raw_value, re.IGNORECASE)
                if match:
                    return match.group(0).replace(" ", "")

        # A normalized gram label is still better than displaying no size.
        if weight_grams is not None:
            return f"{weight_grams}g"
        return None

    def _extract_variants(self, product_data: dict[str, Any]) -> list[CoffeeVariantData]:
        """Convert Shopify variants into stable purchasable catalog options."""
        product_available = bool(product_data.get("available", True))
        product_price = self._extract_price(product_data)
        variants: list[CoffeeVariantData] = []

        for index, raw_variant in enumerate(self._raw_variants(product_data), start=1):
            # Parse weight and bag size first because they drive cart selection.
            weight_grams = self._variant_weight_grams(raw_variant)
            bag_size = self._variant_bag_size(raw_variant, weight_grams)

            # Keep Shopify's human-visible variant title when available.
            raw_title = raw_variant.get("title")
            title = raw_title.strip() if isinstance(raw_title, str) and raw_title.strip() else None

            # Variant price wins over product price; product price is a fallback.
            raw_price = raw_variant.get("price")
            price_cents = self._price_cents(raw_price) or product_price

            # External IDs may arrive as ints or strings depending on endpoint.
            raw_id = raw_variant.get("id")
            variant_id = str(raw_id) if isinstance(raw_id, int | str) and str(raw_id) else None

            variants.append(
                CoffeeVariantData(
                    shopify_variant_id=variant_id,
                    name=title or bag_size or f"Variant {index}",
                    price_cents=price_cents,
                    bag_size=bag_size,
                    weight_grams=weight_grams,
                    availability=bool(raw_variant.get("available", product_available)),
                )
            )
        return variants

    def _smallest_available_variant(self, variants: list[CoffeeVariantData]) -> CoffeeVariantData | None:
        """Choose the lightest in-stock variant with enough data for a cart."""
        # Exclude wholesale/B2B options before choosing the smallest bag.
        available = [variant for variant in variants if variant.availability and is_retail_variant(variant.name)]

        # Weight-aware variants can be compared directly; otherwise fall back to
        # the first available variant from Shopify's source order.
        weighted = [variant for variant in available if variant.weight_grams is not None]
        if weighted:
            return min(weighted, key=lambda variant: variant.weight_grams or 0)
        return available[0] if available else None

    def _extract_bag_size(self, product_data: dict[str, Any]) -> str | None:
        """Find the smallest available bag size in Shopify variants."""
        # Product-level bag size mirrors the cart-default variant when possible.
        selected = self._smallest_available_variant(self._extract_variants(product_data))
        if selected is not None:
            return selected.bag_size

        return None

    def _extract_bag_size_from_description(self, description: str) -> str | None:
        """Read a leading bag size from sparse Shopify variant data."""
        # Narval-style descriptions can begin with "340g" while Shopify reports
        # zero-gram variants. Only trust weights at the very start of the text so
        # recipe ratios or bundle descriptions do not become product bag sizes.
        first_line = next((line.strip() for line in description.splitlines() if line.strip()), "")
        if parse_weight_grams(first_line) is None:
            return None

        match = re.match(r"\s*\d+(?:\.\d+)?\s*(?:g|kg|oz|lbs?)\b", first_line, flags=re.IGNORECASE)
        return match.group(0).replace(" ", "") if match else None
