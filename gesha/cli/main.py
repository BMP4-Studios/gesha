from __future__ import annotations

from typing import Optional

import requests
import typer
from rich.table import Table
from rich.console import Console

from gesha.db.session import get_session, init_db
from gesha.scrapers.demello import DeMelloScraper
from gesha.scrapers.hatch import HatchScraper
from gesha.scrapers.traffic import TrafficScraper
from gesha.services.coffee_service import CoffeeService

app = typer.Typer(help="Local specialty coffee discovery and cart optimization CLI.")
console = Console()


def _print_coffees(coffees: list) -> None:
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("ID", style="dim")
    table.add_column("Roaster")
    table.add_column("Name")
    table.add_column("Process")
    table.add_column("Origin")
    table.add_column("Price")
    table.add_column("Notes")

    for coffee in coffees:
        notes = ", ".join(note.name for note in coffee.tasting_notes)
        price = f"${coffee.price_cents / 100:.2f}" if coffee.price_cents else "n/a"
        table.add_row(
            str(coffee.id),
            coffee.roaster.name,
            coffee.name,
            coffee.process or "n/a",
            coffee.origin or "n/a",
            price,
            notes,
        )

    console.print(table)


@app.command()
def init() -> None:
    """Create local SQLite database tables."""
    init_db()
    console.print("[green]Database initialized.[/green]")


@app.command()
def scrape(source: str = typer.Argument("all", help="Scraper to run: hatch, demello, traffic, or all.")) -> None:
    """Scrape coffees from supported roasters."""
    init_db()
    with get_session() as session:
        service = CoffeeService(session)
        scrapers = []
        if source in ("all", "hatch"):
            scrapers.append(HatchScraper())
        if source in ("all", "demello"):
            scrapers.append(DeMelloScraper())
        if source in ("all", "traffic"):
            scrapers.append(TrafficScraper())

        if not scrapers:
            raise typer.BadParameter("Unsupported source. Use 'hatch', 'demello', 'traffic', or 'all'.")

        for scraper in scrapers:
            console.print(f"[blue]Scraping {scraper.__class__.__name__}...[/blue]")
            try:
                coffees = scraper.scrape()
            except requests.exceptions.RequestException as exc:
                console.print(f"[red]Network error while scraping {scraper.__class__.__name__}: {exc}[/red]")
                raise typer.Exit(code=1)
            except Exception as exc:
                console.print(f"[red]Scraper failed: {exc}[/red]")
                raise typer.Exit(code=1)

            for coffee in coffees:
                service.create_or_update_coffee(coffee)
            console.print(f"[green]Imported {len(coffees)} coffees.[/green]")

        roaster_filter = None
        if source == "hatch":
            roaster_filter = "Hatch Coffee"
        elif source == "demello":
            roaster_filter = "De Mello Coffee"
        elif source == "traffic":
            roaster_filter = "Traffic Coffee"

        console.print("[blue]Listing imported coffees...[/blue]")
        coffees = service.list_coffees(roaster_name=roaster_filter)
        _print_coffees(coffees)


@app.command()
def list(
    process: Optional[str] = typer.Option(None, help="Filter by coffee process."),
    flavor: Optional[str] = typer.Option(None, help="Filter by tasting note."),
    roaster: Optional[str] = typer.Option(None, help="Filter by roaster name."),
    available: Optional[bool] = typer.Option(None, help="Show only available coffees."),
) -> None:
    """List coffees in the local database."""
    with get_session() as session:
        service = CoffeeService(session)
        coffees = service.list_coffees(process=process, flavor=flavor, roaster_name=roaster, available=available)

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("ID", style="dim")
        table.add_column("Roaster")
        table.add_column("Name")
        table.add_column("Process")
        table.add_column("Origin")
        table.add_column("Price")
        table.add_column("Notes")

        for coffee in coffees:
            notes = ", ".join(note.name for note in coffee.tasting_notes)
            price = f"${coffee.price_cents / 100:.2f}" if coffee.price_cents else "n/a"
            table.add_row(str(coffee.id), coffee.roaster.name, coffee.name, coffee.process or "n/a", coffee.origin or "n/a", price, notes)

        console.print(table)


@app.command()
def show(coffee_id: int) -> None:
    """Show details for a single coffee."""
    with get_session() as session:
        service = CoffeeService(session)
        coffee = service.get_coffee_by_id(coffee_id)
        if coffee is None:
            console.print(f"[red]Coffee with ID {coffee_id} not found.[/red]")
            raise typer.Exit(code=1)

        table = Table(show_header=False)
        table.add_row("ID", str(coffee.id))
        table.add_row("Roaster", coffee.roaster.name)
        table.add_row("Name", coffee.name)
        table.add_row("Origin", coffee.origin or "n/a")
        table.add_row("Producer", coffee.producer or "n/a")
        table.add_row("Process", coffee.process or "n/a")
        table.add_row("Varietal", coffee.varietal or "n/a")
        table.add_row("Altitude", coffee.altitude or "n/a")
        table.add_row("Roast style", coffee.roast_style or "n/a")
        table.add_row("Bag size", coffee.bag_size or "n/a")
        table.add_row("Price", f"${coffee.price_cents / 100:.2f}" if coffee.price_cents else "n/a")
        table.add_row("Availability", "yes" if coffee.availability else "no")
        table.add_row("URL", coffee.url or "n/a")
        table.add_row("Tasting notes", ", ".join(note.name for note in coffee.tasting_notes) or "n/a")
        console.print(table)


if __name__ == "__main__":
    app()
