from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from gesha.db.models import Coffee, Roaster, TastingNote
from gesha.models.coffee import CoffeeData


class CoffeeService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_or_update_coffee(self, data: CoffeeData) -> Coffee:
        roaster = self.session.scalar(select(Roaster).where(Roaster.name == data.roaster))
        if roaster is None:
            roaster = Roaster(name=data.roaster)
            self.session.add(roaster)
            self.session.flush()

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

        coffee.tasting_notes.clear()
        for note in data.tasting_notes:
            coffee.tasting_notes.append(TastingNote(name=note))

        self.session.commit()
        self.session.refresh(coffee)
        return coffee

    def list_coffees(
        self,
        process: str | None = None,
        flavor: str | None = None,
        roaster_name: str | None = None,
        available: bool | None = None,
    ) -> list[Coffee]:
        query = select(Coffee).join(Roaster)
        if roaster_name:
            query = query.where(Roaster.name.ilike(f"%{roaster_name}%"))
        if process:
            query = query.where(Coffee.process.ilike(f"%{process}%"))
        if available is not None:
            query = query.where(Coffee.availability == available)
        if flavor:
            query = query.join(Coffee.tasting_notes).where(TastingNote.name.ilike(f"%{flavor}%")).distinct()

        return list(self.session.scalars(query).all())

    def get_coffee_by_id(self, coffee_id: int) -> Coffee | None:
        return self.session.get(Coffee, coffee_id)

    def delete_stale_coffees(self, roaster_name: str, current_urls: Iterable[str]) -> int:
        urls = {url for url in current_urls if url}
        if not urls:
            return 0

        roaster = self.session.scalar(select(Roaster).where(Roaster.name == roaster_name))
        if roaster is None:
            return 0

        stale_coffees = self.session.scalars(
            select(Coffee)
            .where(Coffee.roaster_id == roaster.id)
            .where(or_(Coffee.url.is_(None), Coffee.url.not_in(urls)))
        ).all()

        for coffee in stale_coffees:
            self.session.delete(coffee)

        self.session.commit()
        return len(stale_coffees)
