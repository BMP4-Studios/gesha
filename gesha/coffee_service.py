"""Persistence and catalog-query operations used by CLI commands.

This module keeps SQLAlchemy concerns out of scraping and rendering: scrapers
produce ``CoffeeData`` and the CLI asks this service to save or query it.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from gesha.db.models import Coffee, Roaster, TastingNote
from gesha.coffee_data import CoffeeData


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
            roaster = Roaster(name=data.roaster)
            self.session.add(roaster)
            self.session.flush()

        # Prefer canonical product URLs as identity; fall back for sources that
        # do not expose one consistently.
        coffee = None
        if data.url:
            coffee = self.session.scalar(select(Coffee).where(Coffee.url == data.url))

        if coffee is None:
            coffee = self.session.scalar(
                select(Coffee)
                .where(Coffee.name == data.name)
                .where(Coffee.roaster_id == roaster.id)
            )

        if coffee is None:
            coffee = Coffee(roaster_id=roaster.id, name=data.name)
            self.session.add(coffee)

        # Refresh mutable scraped fields while preserving the stable row ID.
        coffee.name = data.name
        coffee.origin = data.origin
        coffee.producer = data.producer
        coffee.process = data.process
        coffee.varietal = data.varietal
        coffee.altitude = data.altitude
        coffee.roast_style = data.roast_style
        coffee.price_cents = data.price_cents
        coffee.bag_size = data.bag_size
        coffee.url = data.url
        coffee.availability = data.availability
        coffee.roast_date = data.roast_date

        # Tasting notes are replaced because they describe the current listing.
        coffee.tasting_notes.clear()
        for note in data.tasting_notes:
            coffee.tasting_notes.append(TastingNote(name=note))

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
        """Query cached coffees for ``list``/``cache`` output and refresh output."""
        # Start from coffees joined to roasters because most CLI output needs both.
        query = select(Coffee).join(Roaster)

        # Add filters only when requested so the same method powers all listings.
        if roaster_name:
            query = query.where(Roaster.name.ilike(f"%{roaster_name}%"))
        if process:
            query = query.where(Coffee.process.ilike(f"%{process}%"))
        if available is not None:
            query = query.where(Coffee.availability == available)
        if flavour:
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

        for coffee in stale_coffees:
            self.session.delete(coffee)

        self.session.commit()
        return len(stale_coffees)
