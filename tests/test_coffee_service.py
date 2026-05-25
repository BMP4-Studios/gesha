"""Tests for catalog persistence rules that protect and replace cached rows."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gesha.db.models import Base
from gesha.models.coffee import CoffeeData
from gesha.services.coffee_service import CoffeeService


def test_delete_stale_coffees_removes_rows_missing_from_latest_scrape() -> None:
    """A refreshed roaster loses vanished products without affecting others."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True, expire_on_commit=False)

    with Session() as session:
        service = CoffeeService(session)
        kept = service.create_or_update_coffee(
            CoffeeData(
                roaster="Hatch Coffee",
                name="Current Coffee",
                url="https://hatchcrafted.com/shop/current-coffee",
            )
        )
        service.create_or_update_coffee(
            CoffeeData(
                roaster="Hatch Coffee",
                name="Old Coffee",
                url="https://hatchcrafted.com/shop/old-coffee",
            )
        )
        service.create_or_update_coffee(
            CoffeeData(
                roaster="De Mello Coffee",
                name="Other Roaster Coffee",
                url="https://hellodemello.com/products/other",
            )
        )

        removed_count = service.delete_stale_coffees(
            "Hatch Coffee",
            ["https://hatchcrafted.com/shop/current-coffee"],
        )

        coffees = service.list_coffees()
        urls = {coffee.url for coffee in coffees}

    assert removed_count == 1
    assert kept.url in urls
    assert "https://hatchcrafted.com/shop/old-coffee" not in urls
    assert "https://hellodemello.com/products/other" in urls


def test_delete_stale_coffees_skips_empty_url_set() -> None:
    """An empty scrape result cannot erase previously useful cached data."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True, expire_on_commit=False)

    with Session() as session:
        service = CoffeeService(session)
        service.create_or_update_coffee(
            CoffeeData(
                roaster="Hatch Coffee",
                name="Current Coffee",
                url="https://hatchcrafted.com/shop/current-coffee",
            )
        )

        removed_count = service.delete_stale_coffees("Hatch Coffee", [])

        coffees = service.list_coffees()

    assert removed_count == 0
    assert len(coffees) == 1
