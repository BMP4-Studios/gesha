"""Tests for catalog persistence rules that protect and replace cached rows."""

from gesha.coffee_data import CoffeeData
from gesha.coffee_service import CoffeeService
from gesha.db.models import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_delete_stale_coffees_removes_rows_missing_from_latest_scrape() -> None:
    """A refreshed roaster loses vanished products without affecting others."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True, expire_on_commit=False)

    with Session() as session:
        service = CoffeeService(session)
        kept = service.create_or_update_coffee(
            CoffeeData(
                roaster="Test Roaster",
                name="Current Coffee",
                url="https://example.test/current-coffee",
            )
        )
        service.create_or_update_coffee(
            CoffeeData(
                roaster="Test Roaster",
                name="Old Coffee",
                url="https://example.test/old-coffee",
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
            "Test Roaster",
            ["https://example.test/current-coffee"],
        )

        coffees = service.list_coffees()
        urls = {coffee.url for coffee in coffees}

    assert removed_count == 1
    assert kept.url in urls
    assert "https://example.test/old-coffee" not in urls
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
                roaster="Test Roaster",
                name="Current Coffee",
                url="https://example.test/current-coffee",
            )
        )

        removed_count = service.delete_stale_coffees("Test Roaster", [])

        coffees = service.list_coffees()

    assert removed_count == 0
    assert len(coffees) == 1
