"""Persistence and catalog-query operations used by CLI commands.

This module keeps SQLAlchemy concerns out of scraping and rendering: scrapers
produce ``CoffeeData`` and the CLI asks this service to save or query it.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from gesha.coffee_data import CoffeeData
from gesha.db.models import Coffee, CoffeeVariant, Roaster, TastingNote

SCRAPED_COFFEE_FIELDS: tuple[str, ...] = (
    # These fields are owned by scraper output and refreshed on every import.
    # Database-only fields such as primary keys and timestamps stay out of this list.
    "name",
    "origin",
    "producer",
    "process",
    "varietal",
    "altitude",
    "roast_style",
    "price_cents",
    "bag_size",
    "url",
    "availability",
    "roast_date",
)


class CoffeeService:
    """Read and update the local catalog within a caller-owned DB session."""

    def __init__(self, session: Session) -> None:
        """Bind service operations to the transaction scope supplied by the CLI."""
        self.session = session

    def create_or_update_coffee(self, data: CoffeeData) -> Coffee:
        """Insert a newly scraped coffee or update its previously cached row."""
        # Roasters are normalized into a separate table so filtering is stable.
        roaster = self.session.scalar(select(Roaster).where(Roaster.name == data.roaster))
        if roaster is None:
            # Flush immediately so the new roaster has an ID for the coffee row.
            roaster = Roaster(name=data.roaster)
            self.session.add(roaster)
            self.session.flush()

        # Prefer canonical product URLs as identity; fall back for sources that
        # do not expose one consistently.
        coffee = None
        if data.url:
            coffee = self.session.scalar(select(Coffee).where(Coffee.url == data.url))

        # Name + roaster is the fallback identity for rows imported before a URL
        # existed or for future scrapers that cannot provide one.
        if coffee is None:
            coffee = self.session.scalar(
                select(Coffee).where(Coffee.name == data.name).where(Coffee.roaster_id == roaster.id)
            )

        if coffee is None:
            # Create the shell row first; the shared field-refresh loop below
            # fills in all scraper-owned columns for both new and existing rows.
            coffee = Coffee(roaster_id=roaster.id, name=data.name)
            self.session.add(coffee)

        # Refresh mutable scraped fields while preserving the stable row ID.
        for field in SCRAPED_COFFEE_FIELDS:
            setattr(coffee, field, getattr(data, field))

        # Tasting notes are replaced because they describe the current listing.
        coffee.tasting_notes.clear()
        for note in data.tasting_notes:
            coffee.tasting_notes.append(TastingNote(name=note))

        # Variants are replaced as a snapshot because Shopify IDs and
        # availability can change independently from the parent product.
        coffee.variants.clear()
        for variant in data.variants:
            # Variant rows intentionally mirror the latest scrape rather than
            # trying to preserve old variant IDs, prices, or availability.
            coffee.variants.append(
                CoffeeVariant(
                    shopify_variant_id=variant.shopify_variant_id,
                    name=variant.name,
                    price_cents=variant.price_cents,
                    bag_size=variant.bag_size,
                    weight_grams=variant.weight_grams,
                    availability=variant.availability,
                )
            )

        # Commit here so each scraper product is durable even if a later product
        # in the same roaster fails to parse.
        self.session.commit()
        self.session.refresh(coffee)
        return coffee

    def list_coffees(
        self,
        process: str | None = None,
        flavour: str | None = None,
        roaster_name: str | None = None,
        available: bool | None = None,
    ) -> list[Coffee]:
        """Query cached coffees for ``list`` output and refresh output."""
        # Start from coffees joined to roasters because most CLI output needs both.
        query = select(Coffee).join(Roaster)

        # Add filters only when requested so the same method powers all listings.
        if roaster_name:
            # Partial, case-insensitive matching is convenient for CLI use.
            query = query.where(Roaster.name.ilike(f"%{roaster_name}%"))
        if process:
            query = query.where(Coffee.process.ilike(f"%{process}%"))
        if available is not None:
            query = query.where(Coffee.availability == available)
        if flavour:
            # Joining notes can duplicate coffees with multiple matching notes;
            # distinct keeps the table output one row per coffee.
            query = query.join(Coffee.tasting_notes).where(TastingNote.name.ilike(f"%{flavour}%")).distinct()

        return list(self.session.scalars(query).all())

    def get_coffee_by_id(self, coffee_id: int) -> Coffee | None:
        """Load the record displayed by ``gesha show`` and ``gesha debug``."""
        return self.session.get(Coffee, coffee_id)

    def delete_stale_coffees(self, roaster_name: str, current_urls: Iterable[str]) -> int:
        """Remove products absent from a successful current scrape of a roaster."""
        urls = {url for url in current_urls if url}
        # An empty response may indicate a failed/changed website; retain cache
        # rather than interpreting it as proof that all products disappeared.
        if not urls:
            return 0

        roaster = self.session.scalar(select(Roaster).where(Roaster.name == roaster_name))
        if roaster is None:
            return 0

        # Limit deletion to the roaster just refreshed; other sources may not
        # have been included in a single-source scrape.
        stale_coffees = self.session.scalars(
            select(Coffee)
            .where(Coffee.roaster_id == roaster.id)
            .where(or_(Coffee.url.is_(None), Coffee.url.not_in(urls)))
        ).all()

        # SQLAlchemy cascades delete-orphan relationships for notes and variants.
        for coffee in stale_coffees:
            self.session.delete(coffee)

        self.session.commit()
        return len(stale_coffees)
