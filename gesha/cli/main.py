from __future__ import annotations

import concurrent.futures
from typing import Optional

import requests
import typer
from rich.table import Table
from rich.console import Console

from gesha.db.session import get_session, init_db
from gesha.scrapers import get_scrapers, supported_sources
from gesha.services.coffee_service import CoffeeService
from gesha.normalization.normalize import NA_LABEL

app = typer.Typer(help="Local specialty coffee discovery and cart optimization CLI.")
console = Console()


def _print_coffees(coffees: list) -> None:
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("ID", style="dim", justify="right")
    table.add_column("Roaster")
    table.add_column("Name")
    table.add_column("Size")
    table.add_column("Process")
    table.add_column("Origin")
    table.add_column("Price")
    table.add_column("Notes")

    for i, coffee in enumerate(coffees, 1):
        notes = ", ".join(note.name for note in coffee.tasting_notes)
        price = f"${coffee.price_cents / 100:.2f}" if coffee.price_cents else NA_LABEL
        table.add_row(
            str(i),
            str(coffee.id),
            coffee.roaster.name,
            coffee.name,
            coffee.bag_size or NA_LABEL,
            coffee.process or NA_LABEL,
            coffee.origin or NA_LABEL,
            price,
            notes,
        )

    console.print(table)


def _refresh_catalog(source: str) -> None:
    init_db()
    with get_session() as session:
        service = CoffeeService(session)
        if source not in supported_sources():
            supported = "', '".join(supported_sources())
            raise typer.BadParameter(f"Unsupported source. Use '{supported}'.")
        scrapers = get_scrapers(source)
        refreshed_roaster_names = []

        def run_scraper(scraper):
            console.print(f"[blue]Scraping {scraper.SOURCE_NAME}...[/blue]")
            return scraper.SOURCE_NAME, scraper.ROASTER_NAME, scraper.scrape()

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(scrapers)) as executor:
            future_to_scraper = {executor.submit(run_scraper, s): s for s in scrapers}
            for future in concurrent.futures.as_completed(future_to_scraper):
                source_name, roaster_name, scraped_coffees = future.result()

                for coffee in scraped_coffees:
                    service.create_or_update_coffee(coffee)

                if scraped_coffees:
                    refreshed_roaster_names.append(roaster_name)
                    removed_count = service.delete_stale_coffees(
                        roaster_name,
                        [c.url for c in scraped_coffees if c.url],
                    )
                else:
                    removed_count = 0
                    console.print(f"[yellow]No coffees returned for {roaster_name}.[/yellow]")
                console.print(f"[green]Finished {source_name}: {len(scraped_coffees)} imported, {removed_count} stale removed.[/green]")

        console.print("[blue]Listing cleaned coffees...[/blue]")
        if source == "all":
            coffees = [
                coffee
                for coffee in service.list_coffees()
                if coffee.roaster.name in refreshed_roaster_names
            ]
        elif refreshed_roaster_names:
            # If we scraped a single specific source, filter to its roaster name
            coffees = service.list_coffees(roaster_name=refreshed_roaster_names[0])
        else:
            coffees = []
        _print_coffees(coffees)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Refresh and list the Gesha catalog when no subcommand is provided."""
    if ctx.invoked_subcommand is None:
        _refresh_catalog("all")


@app.command()
def init() -> None:
    """Create local SQLite database tables."""
    init_db()
    console.print("[green]Database initialized.[/green]")


@app.command()
def scrape(source: str = typer.Argument("all", help="Scraper to run: demello, traffic, portebleue, colorfull, angry, hatch, or all.")) -> None:
    """Refresh coffees from supported roasters and clean stale rows."""
    _refresh_catalog(source)


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
        _print_coffees(coffees)


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
        table.add_row("Origin", coffee.origin or NA_LABEL)
        table.add_row("Producer", coffee.producer or NA_LABEL)
        table.add_row("Process", coffee.process or NA_LABEL)
        table.add_row("Varietal", coffee.varietal or NA_LABEL)
        table.add_row("Altitude", coffee.altitude or NA_LABEL)
        table.add_row("Roast style", coffee.roast_style or NA_LABEL)
        table.add_row("Bag size", coffee.bag_size or NA_LABEL)
        table.add_row("Price", f"${coffee.price_cents / 100:.2f}" if coffee.price_cents else NA_LABEL)
        table.add_row("Availability", "yes" if coffee.availability else "no")
        table.add_row("URL", coffee.url or NA_LABEL)
        table.add_row("Tasting notes", ", ".join(note.name for note in coffee.tasting_notes) or NA_LABEL)
        console.print(table)


if __name__ == "__main__":
    app()
