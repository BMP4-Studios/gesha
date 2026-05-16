from __future__ import annotations

from typing import Iterable, List, Optional

from sqlalchemy import select
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
        process: Optional[str] = None,
        flavor: Optional[str] = None,
        roaster_name: Optional[str] = None,
        available: Optional[bool] = None,
    ) -> List[Coffee]:
        query = select(Coffee).join(Roaster)
        if roaster_name:
            query = query.where(Roaster.name.ilike(f"%{roaster_name}%"))
        if process:
            query = query.where(Coffee.process.ilike(f"%{process}%"))
        if available is not None:
            query = query.where(Coffee.availability == available)
        coffees = self.session.scalars(query).all()

        if flavor:
            matches: list[Coffee] = []
            for coffee in coffees:
                if any(flavor.lower() in note.name.lower() for note in coffee.tasting_notes):
                    matches.append(coffee)
            coffees = matches

        return coffees

    def get_coffee_by_id(self, coffee_id: int) -> Optional[Coffee]:
        return self.session.get(Coffee, coffee_id)
