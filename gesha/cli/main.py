"""Typer command surface for scraping, caching, and inspecting coffees.

The installed ``gesha`` executable resolves to ``app`` in this module. It
coordinates scrapers and ``CoffeeService`` while Rich handles terminal output.
"""

from __future__ import annotations

import concurrent.futures
from collections.abc import Callable, Sequence
from typing import Any, cast

import requests
import typer
from rich.table import Table
from rich.console import Console

from gesha.db.session import get_session, init_db
from gesha.db.models import Coffee
from gesha.models.coffee import CoffeeData
from gesha.scrapers import get_scrapers, supported_sources
from gesha.scrapers.base import BaseScraper
from gesha.services.coffee_service import CoffeeService
from gesha.normalization.normalize import NA_LABEL

app = typer.Typer(
    help=(
        "Gesha: A local-first specialty coffee discovery tool.\n\n"
        "This CLI scrapes supported Canadian roasters, normalizes their metadata "
        "(origin, process, tasting notes, etc.), and stores the results in a local "
        "SQLite database for fast querying and inspection."
    ),
    rich_markup_mode="rich",
)
console = Console()

TyperParamFactory = Callable[..., Any]
typer_argument = cast(TyperParamFactory, getattr(typer, "Argument"))
typer_option = cast(TyperParamFactory, getattr(typer, "Option"))


def _print_coffees(coffees: Sequence[Coffee]) -> None:
    """Render queried ORM coffee records as the shared CLI catalog table."""
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("ID", style="dim", justify="right")
    table.add_column("Roaster")
    table.add_column("Name")
    table.add_column("Size")
    table.add_column("Process")
    table.add_column("Origin")
    table.add_column("Price")
    table.add_column("Notes")

    # Keep scrape output and cache/list output visually identical by rendering
    # records only after they have been stored and reloaded from the database.
    for coffee in coffees:
        notes = ", ".join(note.name for note in coffee.tasting_notes)
        price = f"${coffee.price_cents / 100:.2f}" if coffee.price_cents else NA_LABEL
        name_display = f"[link={coffee.url}]{coffee.name}[/link]" if coffee.url else coffee.name
        table.add_row(
            str(coffee.id),
            coffee.roaster.name,
            name_display,
            coffee.bag_size or NA_LABEL,
            coffee.process or NA_LABEL,
            coffee.origin or NA_LABEL,
            price,
            notes or NA_LABEL,
        )

    console.print(table)


def _refresh_catalog(source: str) -> None:
    """Scrape one or all sources, persist results, and print refreshed records."""
    # Create the database on first execution so a refresh is immediately usable.
    init_db()

    with get_session() as session:
        service = CoffeeService(session)

        if source not in supported_sources():
            valid_sources = sorted([s for s in supported_sources() if s != "all"])
            console.print(f"[red]Error: '{source}' is not a supported roaster.[/red]")
            console.print("\n[bold]Available roasters:[/bold]")

            for s in valid_sources:
                console.print(f" - {s}")

            console.print(" - all")
            raise typer.Exit(code=1)

        scrapers = get_scrapers(source)
        refreshed_roaster_names: list[str] = []

        def run_scraper(scraper: BaseScraper) -> tuple[str, str, list[CoffeeData]]:
            """Run a network scraper in a worker and retain source identity."""
            console.print(f"[blue]Scraping {scraper.SOURCE_NAME}...[/blue]")
            return scraper.SOURCE_NAME, scraper.ROASTER_NAME, scraper.scrape()

        # Each roaster is independent, so fetch sources concurrently while
        # serializing database writes in the owning command/session thread.
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(scrapers)) as executor:
            future_to_scraper = {executor.submit(run_scraper, s): s for s in scrapers}
            for future in concurrent.futures.as_completed(future_to_scraper):
                source_name, roaster_name, scraped_coffees = future.result()

                # Upsert current products before trimming rows no longer found
                # on this successfully returned roaster listing.
                for coffee in scraped_coffees:
                    service.create_or_update_coffee(coffee)

                if scraped_coffees:
                    refreshed_roaster_names.append(roaster_name)
                    current_urls = [coffee.url for coffee in scraped_coffees if coffee.url]
                    removed_count = service.delete_stale_coffees(roaster_name, current_urls)
                else:
                    removed_count = 0
                    console.print(f"[yellow]No coffees returned for {roaster_name}.[/yellow]")

                console.print(f"[green]Finished {source_name}: {len(scraped_coffees)} imported, {removed_count} stale removed.[/green]")

        console.print("[blue]Listing cleaned coffees...[/blue]")
        # An all-source refresh displays only successfully returned roasters;
        # cached rows for a failed source remain protected but are not implied
        # to have been refreshed during this invocation.
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
    """Create local SQLite database tables without running a scrape."""
    init_db()
    console.print("[green]Database initialized.[/green]")


@app.command()
def scrape(
    source: str = typer_argument(
        "all", 
        help="The specific roaster to scrape (e.g., 'traffic') or 'all' to refresh the entire catalog."
    )
) -> None:
    """
    Refresh the local database by scraping roaster websites.
    
    This command fetches product data, normalizes it, updates existing records, 
    and deletes coffees that are no longer available on the roaster's site.
    It is also the network-backed counterpart to the read-only ``cache`` command."""
    _refresh_catalog(source)


def _query_cached_coffees(
    process: str | None,
    flavour: str | None,
    roaster: str | None,
    available: bool | None,
) -> None:
    """Print cached rows for the read-only ``list`` and ``cache`` commands."""
    with get_session() as session:
        service = CoffeeService(session)
        coffees = service.list_coffees(process=process, flavour=flavour, roaster_name=roaster, available=available)
        _print_coffees(coffees)


@app.command(name="cache")
def cache_coffees_command(
    process: str | None = typer_option(None, help="Filter by coffee process."),
    flavour: str | None = typer_option(None, help="Filter by tasting note."),
    roaster: str | None = typer_option(None, help="Filter by roaster name."),
    available: bool | None = typer_option(None, help="Show only available coffees."),
) -> None:
    """Relist previously scraped coffees without contacting roaster websites."""
    _query_cached_coffees(process, flavour, roaster, available)


@app.command(name="list")
def list_coffees_command(
    process: str | None = typer_option(None, help="Filter by coffee process."),
    flavour: str | None = typer_option(None, help="Filter by tasting note."),
    roaster: str | None = typer_option(None, help="Filter by roaster name."),
    available: bool | None = typer_option(None, help="Show only available coffees."),
) -> None:
    """List and filter cached coffees; equivalent to ``gesha cache``."""
    _query_cached_coffees(process, flavour, roaster, available)


@app.command()
def show(coffee_id: int) -> None:
    """Show one cached coffee record selected by its table ID."""
    with get_session() as session:
        service = CoffeeService(session)
        coffee = service.get_coffee_by_id(coffee_id)
        if coffee is None:
            console.print(f"[red]Coffee with ID {coffee_id} not found.[/red]")
            raise typer.Exit(code=1)

        table = Table(show_header=False)
        table.add_row("ID", str(coffee.id))
        table.add_row("Roaster", coffee.roaster.name)
        name_display = f"[link={coffee.url}]{coffee.name}[/link]" if coffee.url else coffee.name
        table.add_row("Name", name_display)
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


@app.command()
def debug(coffee_id: int) -> None:
    """Fetch raw source responses for a cached coffee to help parser debugging."""

    with get_session() as session:
        service = CoffeeService(session)
        coffee = service.get_coffee_by_id(coffee_id)

        if coffee is None:
            console.print(f"[red]Coffee with ID {coffee_id} not found.[/red]")
            raise typer.Exit(code=1)

        if not coffee.url:
            console.print(f"[red]Coffee with ID {coffee_id} has no URL to debug.[/red]")
            raise typer.Exit(code=1)

        filename = f"debug/debug_{coffee_id}.txt"
        output : list[str] = []

        # Capture a Shopify-style JSON response when supported; a missing JSON
        # endpoint is tolerated because non-Shopify records are also debuggable.
        json_url = f"{coffee.url}.js" if not coffee.url.endswith(".js") else coffee.url
        res_json = requests.get(json_url, timeout=15)
        if res_json.status_code == 200:
            output.append("=== RAW JSON DATA ===\n")
            output.append(res_json.text)
            output.append("\n\n")

        # The HTML response is always included because each parser may depend
        # on selectors or embedded page payloads not represented in JSON.
        res_html = requests.get(coffee.url, timeout=15)
        res_html.raise_for_status()
        output.append("=== RAW HTML DATA ===\n")
        output.append(res_html.text)

        with open(filename, "w", encoding="utf-8") as f:
            f.writelines(output)

        console.print(f"[green]Full raw data dumped to {filename}[/green]")


if __name__ == "__main__":
    app()
