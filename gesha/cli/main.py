"""Typer command surface for scraping, caching, and inspecting coffees.

The installed ``gesha`` executable resolves to ``app`` in this module. It
coordinates scrapers and ``CoffeeService`` while Rich handles terminal output.
"""

from __future__ import annotations

import concurrent.futures
import logging
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

import requests
import typer
from gesha.cart import (
    CartCandidate,
    build_cart_permalink,
    cart_item_for_coffee,
    read_preference_config,
    recommend_carts,
    smallest_available_variant,
)
from gesha.coffee_data import CoffeeData
from gesha.coffee_service import CoffeeService
from gesha.db.models import Coffee
from gesha.db.session import get_session, init_db
from gesha.measurements import parse_weight_grams, price_per_100g_cents
from gesha.normalization import NA_LABEL, price_display
from gesha.scrapers import get_scraper, get_scrapers, supported_sources
from gesha.scrapers.base_scraper import BaseScraper
from gesha.shipping import SHIPPING_POLICIES, Destination, resolve_destination, resolve_shipping_threshold
from rich.align import Align
from rich.console import Console
from rich.table import Table
from rich.text import Text

app = typer.Typer(
    # Typer reads this object to build the installed ``gesha`` command.
    help=(
        "Gesha: A local-first specialty coffee discovery tool.\n\n"
        "This CLI scrapes supported Canadian roasters, normalizes their metadata "
        "(origin, process, tasting notes, etc.), and stores the results in a local "
        "SQLite database for querying, comparison, and cart recommendations."
    ),
    rich_markup_mode="rich",
)
console = Console()
DEFAULT_PREFERENCES_PATH = Path("cart_preferences.txt")
LOG_PATH = Path("gesha.log")

# Typer's type stubs are stricter than its runtime API. These aliases keep
# command signatures readable while avoiding noisy type-checking false positives.
TyperParamFactory = Callable[..., Any]
typer_argument = cast(TyperParamFactory, typer.Argument)
typer_option = cast(TyperParamFactory, typer.Option)

# Reuse the same option object anywhere a command accepts the preferences file.
preferences_file_option = typer_option(
    DEFAULT_PREFERENCES_PATH,
    "--preferences",
    "-p",
    help="Text file containing include/exclude preference keywords and optional destination settings.",
)


def _configure_logging() -> None:
    """Send concise warnings to the terminal and full diagnostics to a log file."""
    root_logger = logging.getLogger()
    if any(handler.get_name().startswith("gesha-cli-") for handler in root_logger.handlers):
        return

    # Let handlers decide what to emit: warnings reach the terminal, while debug
    # diagnostics are retained only in the local log file.
    root_logger.setLevel(logging.DEBUG)

    stream_handler = logging.StreamHandler()
    stream_handler.set_name("gesha-cli-terminal")
    stream_handler.setLevel(logging.WARNING)
    stream_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.set_name("gesha-cli-file")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root_logger.addHandler(file_handler)


def _coffee_price_per_100g_cents(coffee: Coffee) -> int | None:
    """Calculate unit price from the smallest variant or legacy bag fields."""
    # Prefer variant rows because they are the source of truth for cart links.
    variant = smallest_available_variant(coffee)
    if variant is not None:
        return price_per_100g_cents(variant.price_cents, variant.weight_grams)

    # Older or partially scraped rows may still only have product-level fields.
    return price_per_100g_cents(coffee.price_cents, parse_weight_grams(coffee.bag_size))


def _print_coffees(coffees: Sequence[Coffee]) -> None:
    """Render queried ORM coffee records as the shared CLI catalog table."""
    # Build the stable table shape used by scrape, cache, and list output.
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("ID", style="dim", justify="right")
    table.add_column("Roaster")
    table.add_column("Name")
    table.add_column("Size")
    table.add_column("Process")
    table.add_column("Origin")
    table.add_column("Price")
    table.add_column("$/100g")
    table.add_column("Notes")

    # Keep scrape output and cache/list output visually identical by rendering
    # records only after they have been stored and reloaded from the database.
    for coffee in coffees:
        notes = ", ".join(note.name for note in coffee.tasting_notes)
        name_display = f"[link={coffee.url}]{coffee.name}[/link]" if coffee.url else coffee.name
        table.add_row(
            str(coffee.id),
            coffee.roaster.name,
            name_display,
            coffee.bag_size or NA_LABEL,
            coffee.process or NA_LABEL,
            coffee.origin or NA_LABEL,
            price_display(coffee.price_cents),
            price_display(_coffee_price_per_100g_cents(coffee)),
            notes or NA_LABEL,
        )

    console.print(table)


def _refresh_catalog(source: str) -> None:
    """Scrape one or all sources, persist results, and print refreshed records."""
    # Create the database on first execution so a refresh is immediately usable.
    init_db()

    with get_session() as session:
        service = CoffeeService(session)

        # Validate user input before starting any network work.
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

                console.print(
                    f"[green]Finished {source_name}: {len(scraped_coffees)} imported, "
                    f"{removed_count} stale removed.[/green]"
                )

        console.print("[blue]Listing cleaned coffees...[/blue]")
        # An all-source refresh displays only successfully returned roasters;
        # cached rows for a failed source remain protected but are not implied
        # to have been refreshed during this invocation.
        if source == "all":
            coffees = [coffee for coffee in service.list_coffees() if coffee.roaster.name in refreshed_roaster_names]
        elif refreshed_roaster_names:
            # If we scraped a single specific source, filter to its roaster name
            coffees = service.list_coffees(roaster_name=refreshed_roaster_names[0])
        else:
            coffees = []
        _print_coffees(coffees)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Refresh and list the Gesha catalog when no subcommand is provided."""
    _configure_logging()

    # Typer invokes callbacks for both ``gesha`` and ``gesha <subcommand>``. The
    # guard makes the default refresh/cart workflow run only when no subcommand
    # was selected.
    if ctx.invoked_subcommand is None:
        _refresh_catalog("all")

        # Call the command function with real defaults. Passing Typer's option
        # objects through here would leak CLI metadata into normal Python code.
        cart(
            source="all",
            preferences=DEFAULT_PREFERENCES_PATH,
            province=None,
            postal_code=None,
            threshold=None,
            max_bags=6,
            refresh_shipping=True,
        )


@app.command()
def init() -> None:
    """Create local SQLite database tables without running a scrape."""
    # This is useful when checking the DB schema or preparing a fresh checkout.
    init_db()
    console.print("[green]Database initialized.[/green]")


@app.command()
def scrape(
    source: str = typer_argument(
        "all",
        help="The specific roaster to scrape (e.g., 'traffic') or 'all' to refresh the entire catalog.",
    ),
) -> None:
    """Refresh the local database by scraping roaster websites.

    This command fetches product data, normalizes it, updates existing records,
    and deletes coffees that are no longer available on the roaster's site.
    It is also the network-backed counterpart to the read-only ``cache`` command.
    """
    # All scrape orchestration lives in one helper so the no-argument callback
    # and explicit ``gesha scrape`` command behave the same way.
    _refresh_catalog(source)


def _query_cached_coffees(
    process: str | None,
    flavour: str | None,
    roaster: str | None,
    available: bool | None,
) -> None:
    """Print cached rows for the read-only ``list`` and ``cache`` commands."""
    # Open a short read session so cached queries do not depend on scrape state.
    with get_session() as session:
        service = CoffeeService(session)
        coffees = service.list_coffees(
            process=process,
            flavour=flavour,
            roaster_name=roaster,
            available=available,
        )
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
    # Open a read session for the lifetime of the rendered ORM object.
    with get_session() as session:
        service = CoffeeService(session)

        # Look up the row first so missing IDs fail before rendering starts.
        coffee = service.get_coffee_by_id(coffee_id)
        if coffee is None:
            console.print(f"[red]Coffee with ID {coffee_id} not found.[/red]")
            raise typer.Exit(code=1)

        # Render the full record vertically so sparse metadata stays readable.
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
        table.add_row("Price", price_display(coffee.price_cents))
        table.add_row("Price / 100g", price_display(_coffee_price_per_100g_cents(coffee)))
        table.add_row("Availability", "yes" if coffee.availability else "no")
        table.add_row("URL", coffee.url or NA_LABEL)
        table.add_row("Tasting notes", ", ".join(note.name for note in coffee.tasting_notes) or NA_LABEL)
        console.print(table)


def _print_cart_candidate(
    candidate: CartCandidate,
    destination: Destination,
) -> None:
    """Render one ranked recommendation and its Shopify cart permalink."""
    # Each recommendation is its own table because the cart subtotal and
    # threshold overspend are part of the recommendation, not per-item data.
    table = Table(
        title=f"Cart: {price_display(candidate.subtotal_cents)} ({price_display(candidate.overspend_cents)} over threshold)",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Coffee")
    table.add_column("Size")
    table.add_column("Process")
    table.add_column("Origin")
    table.add_column("Price", justify="right")
    table.add_column("$/100g", justify="right")
    table.add_column("Notes")
    table.add_column("Matches")

    # Items are already sorted by recommendation strength inside ``CartCandidate``.
    for item in candidate.items:
        name_display = f"[link={item.product_url}]{item.name}[/link]"
        table.add_row(
            name_display,
            item.bag_size,
            item.process or NA_LABEL,
            item.origin or NA_LABEL,
            price_display(item.price_cents),
            price_display(item.price_per_100g_cents),
            ", ".join(item.tasting_notes) or NA_LABEL,
            ", ".join(item.matched_keywords),
        )

    console.print(table)
    console.print(f"Preference keywords covered: {', '.join(candidate.matched_keywords)}")

    # The cart link is optional because older cached rows may lack Shopify
    # variant IDs; the recommendation itself can still be useful without it.
    cart_url = build_cart_permalink(candidate, destination)
    if cart_url:
        console.print(f"[link={cart_url}][bold blue]Open cart![/bold blue][/link]")
    else:
        console.print(
            "[yellow]No pre-filled cart link is available. Refresh this roaster to store current Shopify variant IDs.[/yellow]"
        )


@app.command()
def cart(
    source: str = typer_argument(
        "all",
        help="The roaster to optimize (e.g., 'traffic') or 'all' for every supported roaster.",
    ),
    preferences: Path = preferences_file_option,
    province: str | None = typer_option(
        None,
        "--province",
        help="Canadian province or territory abbreviation; defaults to ON.",
    ),
    postal_code: str | None = typer_option(
        None,
        "--postal-code",
        help="Canadian postal code used to infer the province and prefill checkout.",
    ),
    threshold: float | None = typer_option(
        None,
        "--threshold",
        min=0.01,
        help="Override the published free-shipping threshold in CAD.",
    ),
    max_bags: int = typer_option(
        6,
        "--max-bags",
        min=1,
        help="Maximum number of distinct smallest-size bags in a recommendation.",
    ),
    refresh_shipping: bool = typer_option(
        True,
        "--refresh-shipping/--no-refresh-shipping",
        help="Check roaster shipping pages before using configured fallback thresholds.",
    ),
) -> None:
    """Recommend preference-matched carts that reach free shipping."""
    # Keep source validation before preference parsing so typo errors are clear.
    if source not in supported_sources():
        console.print(f"[red]Error: '{source}' is not a supported roaster.[/red]")
        raise typer.Exit(code=1)

    try:
        # The default preferences file is optional, but an explicitly provided
        # path should fail loudly if it does not exist.
        if preferences != DEFAULT_PREFERENCES_PATH and not preferences.exists():
            raise ValueError(f"Preference file not found: {preferences}")
        preference_config = read_preference_config(preferences)

        # CLI flags override file directives. A postal code can infer province,
        # so ignore the file province when an explicit postal code is supplied.
        selected_postal_code = postal_code or preference_config.postal_code
        selected_province = province if province is not None else (None if postal_code else preference_config.province)
        destination = resolve_destination(
            province=selected_province,
            postal_code=selected_postal_code,
        )
    except ValueError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    if not preference_config.keywords:
        console.print("[red]Error: Add at least one preference keyword.[/red]")
        raise typer.Exit(code=1)

    # The shipping policy table is keyed by roaster display names, while CLI
    # arguments use short source keys such as ``traffic``.
    selected_roasters = list(SHIPPING_POLICIES) if source == "all" else [get_scraper(source).ROASTER_NAME]
    override_cents = round(threshold * 100) if threshold is not None else None

    init_db()
    with get_session() as session:
        service = CoffeeService(session)
        coffees = service.list_coffees(available=True)
        shipping_thresholds = {}

        # Shipping lookups are independent per roaster, so run them concurrently
        # without mixing them into the database session work.
        if override_cents is None:
            roasters_with_coffee = {
                roaster_name
                for roaster_name in selected_roasters
                if any(coffee.roaster.name == roaster_name for coffee in coffees)
            }
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(roasters_with_coffee) or 1) as executor:
                threshold_futures = {
                    roaster_name: executor.submit(
                        resolve_shipping_threshold,
                        roaster_name,
                        destination,
                        refresh=refresh_shipping,
                    )
                    for roaster_name in roasters_with_coffee
                }
                shipping_thresholds = {
                    roaster_name: future.result() for roaster_name, future in threshold_futures.items()
                }

        # Print the fixed header before per-roaster sections so empty roasters
        # still make it clear which destination/preferences were used.
        console.print()
        console.print(
            Align.center(
                Text(
                    "----------==========********** Gesha Cart Recommendations **********==========----------",
                    style="bold cyan",
                )
            )
        )
        console.print(
            f"\n[bold]Destination:[/bold] {destination.province}, Canada"
            + (f" {destination.postal_code}" if destination.postal_code else "")
        )
        console.print(f"[bold]Preference keywords:[/bold] {', '.join(preference_config.keywords)}")
        if preference_config.excluded_keywords:
            console.print(f"[bold]Excluded keywords:[/bold] {', '.join(preference_config.excluded_keywords)}")

        for roaster_name in selected_roasters:
            # Work one roaster at a time because Shopify carts cannot mix stores.
            roaster_coffees = [coffee for coffee in coffees if coffee.roaster.name == roaster_name]
            if not roaster_coffees:
                console.print(f"\n[yellow]{roaster_name}: no cached available coffees.[/yellow]")
                continue

            # A manual threshold is useful when the live policy page is missing,
            # ambiguous, or temporarily unavailable.
            if override_cents is not None:
                threshold_cents = override_cents
                threshold_source = "command-line override"
                policy_url = None
            else:
                shipping_threshold = shipping_thresholds.get(roaster_name)
                if shipping_threshold is None:
                    console.print(f"\n[yellow]{roaster_name}: no Canadian shipping policy is configured.[/yellow]")
                    continue
                threshold_cents = shipping_threshold.amount_cents
                threshold_source = "live policy page" if shipping_threshold.detected_live else "configured fallback"
                policy_url = shipping_threshold.policy_url

            # Convert cached coffees into optimizer items. Coffees with no
            # preference match, excluded keywords, or missing variant data drop out.
            items = [
                item
                for coffee in roaster_coffees
                if (
                    item := cart_item_for_coffee(
                        coffee,
                        preference_config.keywords,
                        preference_config.excluded_keywords,
                    )
                )
                is not None
            ]

            # We currently show one best cart per roaster; internals still rank
            # candidates so this can be expanded later without changing scoring.
            candidates = recommend_carts(
                items,
                threshold_cents,
                max_bags=max_bags,
                limit=1,
                keyword_priority=preference_config.keywords,
            )

            console.print(f"\n[bold cyan]{roaster_name}[/bold cyan]")
            console.print(f"Estimated free-shipping threshold: {price_display(threshold_cents)} ({threshold_source})")
            if policy_url:
                console.print(f"Policy: [link={policy_url}]{policy_url}[/link]")

            if not candidates:
                console.print(
                    "[yellow]No matching combination reaches the threshold with the current keywords, exclusions, "
                    "and bag limit. A fresh scrape may also be needed to populate variant weights and prices.[/yellow]"
                )
                continue

            _print_cart_candidate(candidates[0], destination)


@app.command()
def debug(coffee_id: int) -> None:
    """Fetch raw source responses for a cached coffee to help parser debugging."""

    # The cached row gives us the canonical URL that the scraper stored.
    with get_session() as session:
        service = CoffeeService(session)
        coffee = service.get_coffee_by_id(coffee_id)

        if coffee is None:
            console.print(f"[red]Coffee with ID {coffee_id} not found.[/red]")
            raise typer.Exit(code=1)

        if not coffee.url:
            console.print(f"[red]Coffee with ID {coffee_id} has no URL to debug.[/red]")
            raise typer.Exit(code=1)

        # One debug file contains both JSON and HTML so parser fixtures can be
        # derived from a single capture when a roaster changes its page shape.
        output_path = Path("debug") / f"debug_{coffee_id}.txt"
        output_path.parent.mkdir(exist_ok=True)
        output: list[str] = []

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

        output_path.write_text("".join(output), encoding="utf-8")

        console.print(f"[green]Full raw data dumped to {output_path}[/green]")


@app.command(name="test")
def test_command() -> None:
    """Run the project test suite through pytest."""
    console.print("[blue]Running tests...[/blue]")

    # Delegate to the active Python executable so the current venv is used.
    result = subprocess.run([sys.executable, "-m", "pytest"], check=False)
    raise typer.Exit(code=result.returncode)


if __name__ == "__main__":
    app()
