"""Typer command surface for scraping, caching, and inspecting coffees.

The installed ``gesha`` executable resolves to ``app`` in this module. It
coordinates scrapers and ``CoffeeService`` while Rich handles terminal output.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import re
import sqlite3
import subprocess
import sys
from collections.abc import Callable, Sequence
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import requests
import typer
from gesha.cart import (
    MAX_CART_BAG_WEIGHT_GRAMS,
    CartCandidate,
    PreferenceConfig,
    build_cart_permalink,
    cart_item_for_coffee,
    matched_keywords,
    read_preference_config,
    recommend_carts,
    smallest_available_variant,
)
from gesha.coffee_data import CoffeeData
from gesha.coffee_service import CoffeeService
from gesha.db.models import Coffee, CoffeeVariant
from gesha.db.session import DB_PATH, engine, get_session, init_db
from gesha.measurements import is_retail_variant, parse_weight_grams, price_per_100g_cents
from gesha.normalization import NA_LABEL, price_display
from gesha.scrapers import get_scraper, get_scrapers, supported_sources
from gesha.scrapers.base_scraper import BaseScraper
from gesha.shipping import Destination, resolve_destination, resolve_shipping_threshold
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

# Raw scraper artifacts live under one ignored directory so repeated debugging
# does not scatter large JSON/HTML files through the repo root.
DEBUG_DIR = Path("debug")

# The default pattern is intentionally broad; callers can pass exact visible
# notes when tracking a specific missing-note bug from a product page.
DEFAULT_TASTING_NOTES_DEBUG_PATTERN = r"notes?|tasting|flavou?r|profile|cup"

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
collection_json_output_dir_option = typer_option(
    DEBUG_DIR,
    "--output-dir",
    help="Directory where <roaster>.json should be written; defaults to debug/.",
)

# These options are shared by the tasting-note diagnostic command so its defaults
# stay visible near the rest of the CLI's reusable option definitions.
tasting_notes_debug_search_option = typer_option(
    DEFAULT_TASTING_NOTES_DEBUG_PATTERN,
    "--search",
    "-s",
    help="Case-insensitive regex used to print matching lines from downloaded debug files.",
)
tasting_notes_debug_limit_option = typer_option(
    5,
    "--limit",
    min=1,
    help="Maximum number of cached coffees missing tasting notes to dump with gesha debug.",
)
rebuild_yes_option = typer_option(
    False,
    "--yes",
    "-y",
    help="Skip the confirmation prompt before replacing the local database.",
)
rebuild_backup_dir_option = typer_option(
    Path("backups"),
    "--backup-dir",
    help="Directory where the current database backup should be written.",
)
rebuild_no_scrape_option = typer_option(
    False,
    "--no-scrape",
    help="Back up and recreate an empty database without scraping roaster websites.",
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


def _read_preferences_for_command(preferences: Path) -> PreferenceConfig:
    """Load preference config and preserve explicit missing-file errors."""
    # The default preferences file is optional, but an explicitly provided path
    # should fail loudly if it does not exist.
    if preferences != DEFAULT_PREFERENCES_PATH and not preferences.exists():
        raise ValueError(f"Preference file not found: {preferences}")
    return read_preference_config(preferences)


def _print_coffees(coffees: Sequence[Coffee]) -> None:
    """Render queried ORM coffee records as the shared CLI catalog table."""
    # Build the stable table shape used by scrape, cache, and list output.
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("ID", style="dim", justify="right")
    table.add_column("Roaster")
    table.add_column("Name")
    table.add_column("Size")
    table.add_column("Avail")
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
            "y" if coffee.availability else "[red]NO[/red]",
            coffee.process or NA_LABEL,
            coffee.origin or NA_LABEL,
            price_display(coffee.price_cents),
            price_display(_coffee_price_per_100g_cents(coffee)),
            notes or NA_LABEL,
        )

    console.print(table)


def _scraper_for_roaster_name(roaster_name: str) -> BaseScraper | None:
    """Find the configured scraper that owns one display roaster name."""
    # Cached rows store display names such as "Traffic Coffee", while CLI
    # source arguments use keys such as "traffic".
    for scraper in get_scrapers("all"):
        if scraper.ROASTER_NAME == roaster_name:
            return scraper
    return None


def _selected_cart_roaster_names(source: str) -> list[str]:
    """Resolve a cart source argument through the scraper registry."""
    # The scraper registry defines supported roasters. Shipping policies are a
    # secondary lookup and should not decide which roasters appear in cart all.
    if source == "all":
        return [scraper.ROASTER_NAME for scraper in get_scrapers("all")]
    return [get_scraper(source).ROASTER_NAME]


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
                scraper = future_to_scraper[future]
                try:
                    source_name, roaster_name, scraped_coffees = future.result()
                except Exception as exc:
                    # Keep full exception details in the log file while letting
                    # the other roasters finish normally.
                    logging.getLogger(__name__).debug(
                        "Scraper failed for %s",
                        scraper.SOURCE_NAME,
                        exc_info=True,
                    )
                    console.print(f"[red]Failed {scraper.SOURCE_NAME}: {exc}[/red]")
                    continue

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


def _backup_path_for(db_path: Path, backup_dir: Path) -> Path:
    """Build an unused timestamped backup path for the current database."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = backup_dir / f"{db_path.stem}-{timestamp}{db_path.suffix}"
    if not candidate.exists():
        return candidate

    # If two rebuilds happen in the same second, keep both backups.
    for suffix in range(2, 100):
        candidate = backup_dir / f"{db_path.stem}-{timestamp}-{suffix}{db_path.suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError("Could not find an unused database backup filename.")


def _backup_database(db_path: Path, backup_dir: Path) -> Path | None:
    """Copy the current SQLite database into the backup directory."""
    if not db_path.exists():
        return None

    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = _backup_path_for(db_path, backup_dir)

    # SQLite's backup API captures a consistent database image, including data
    # that may currently be represented through WAL bookkeeping.
    with closing(sqlite3.connect(str(db_path))) as source:
        with closing(sqlite3.connect(str(backup_path))) as destination:
            source.backup(destination)
    return backup_path


def _sqlite_database_files(db_path: Path) -> tuple[Path, Path, Path, Path]:
    """Return the main SQLite file and sidecar files that should be reset."""
    return (
        db_path,
        db_path.with_name(f"{db_path.name}-wal"),
        db_path.with_name(f"{db_path.name}-shm"),
        db_path.with_name(f"{db_path.name}-journal"),
    )


def _remove_database_files(db_path: Path) -> None:
    """Dispose SQLAlchemy connections and remove the current SQLite files."""
    engine.dispose()
    for path in _sqlite_database_files(db_path):
        if path.exists():
            path.unlink()


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


@app.command()
def rebuild(
    yes: bool = rebuild_yes_option,
    backup_dir: Path = rebuild_backup_dir_option,
    no_scrape: bool = rebuild_no_scrape_option,
) -> None:
    """Back up, wipe, recreate, and refresh the local database."""
    # Rebuild is destructive to the local cache, so require confirmation unless
    # automation explicitly supplied ``--yes``.
    if not yes:
        confirmed = typer.confirm(
            f"Back up and replace {DB_PATH}? This will remove the current local cache before scraping."
        )
        if not confirmed:
            console.print("[yellow]Rebuild cancelled.[/yellow]")
            raise typer.Exit(code=1)

    # Capture a consistent backup before deleting the SQLite database files.
    backup_path = _backup_database(DB_PATH, backup_dir)
    if backup_path is None:
        console.print(f"[yellow]No existing {DB_PATH} found; starting from a fresh database.[/yellow]")
    else:
        console.print(f"[green]Backed up {DB_PATH} to {backup_path}[/green]")

    # Remove the active cache and recreate just the empty schema.
    _remove_database_files(DB_PATH)
    init_db()
    console.print("[green]Database recreated.[/green]")

    # ``--no-scrape`` leaves the user with a clean empty cache for inspection.
    if no_scrape:
        console.print("[yellow]Skipped scrape because --no-scrape was provided.[/yellow]")
        return

    _refresh_catalog("all")


@app.command(name="json")
def collection_json(
    source: str = typer_argument(
        ...,
        help="The specific Shopify roaster collection to download (e.g., 'traffic').",
    ),
    output_dir: Path = collection_json_output_dir_option,
) -> None:
    """Download one roaster's Shopify collection JSON feed to ``<source>.json``."""
    from gesha.scrapers.shopify_scraper import ShopifyScraper

    # ``all`` is useful for scraping, but this command is meant for inspecting
    # one exact raw feed at a time so failures stay obvious.
    valid_sources = sorted([name for name in supported_sources() if name != "all"])
    if source not in valid_sources:
        console.print(f"[red]Error: '{source}' is not a supported roaster for collection JSON download.[/red]")
        console.print("\n[bold]Available roasters:[/bold]")
        for valid_source in valid_sources:
            console.print(f" - {valid_source}")
        raise typer.Exit(code=1)

    scraper = get_scraper(source)
    if not isinstance(scraper, ShopifyScraper):
        console.print(f"[red]Error: '{source}' does not use Shopify collection JSON.[/red]")
        raise typer.Exit(code=1)

    # Use the same browser-impersonating scraper session as normal scraping.
    collection_json_url = scraper._collection_products_json_url()
    response = scraper.session.get(collection_json_url, timeout=15)
    if response.status_code >= 400:
        scraper._log_http_failure("download Shopify collection JSON", collection_json_url, response)
        raise typer.Exit(code=1)
    response.raise_for_status()

    # Pretty-print real JSON so it is useful in an editor. If a storefront
    # returns unexpected non-JSON text, still write it for debugging.
    output_text = response.text
    try:
        parsed_json = json.loads(response.text)
    except json.JSONDecodeError:
        console.print("[yellow]Response was not valid JSON; writing the raw response body.[/yellow]")
    else:
        output_text = f"{json.dumps(parsed_json, indent=2, ensure_ascii=False)}\n"

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{source}.json"
    output_path.write_text(output_text, encoding="utf-8")

    console.print(f"[green]Collection JSON saved to {output_path}[/green]")


def _matching_debug_lines(path: Path, pattern: re.Pattern[str], limit: int = 10) -> list[tuple[int, str]]:
    """Return bounded regex matches from a debug artifact."""
    matches: list[tuple[int, str]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        if pattern.search(line):
            # Keep terminal diagnostics readable even when Shopify embeds huge HTML fields.
            matches.append((line_number, line[:300]))
            if len(matches) >= limit:
                break
    return matches


def _print_debug_matches(path: Path, pattern: re.Pattern[str]) -> None:
    """Show high-signal lines from one generated debug file."""
    matches = _matching_debug_lines(path, pattern)
    if not matches:
        console.print(f"[yellow]No matches for /{pattern.pattern}/ in {path}.[/yellow]")
        return

    console.print(f"[green]Matches in {path}:[/green]")
    for line_number, line in matches:
        console.print(f" - {line_number}: {line}")


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
    threshold_delta = candidate.overspend_cents
    threshold_text = (
        f"{price_display(threshold_delta)} over threshold"
        if threshold_delta >= 0
        else f"{price_display(abs(threshold_delta))} under threshold"
    )

    # Each recommendation is its own table because the cart subtotal and
    # threshold delta are part of the recommendation, not per-item data.
    table = Table(
        title=f"Cart: {price_display(candidate.subtotal_cents)} ({threshold_text})",
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


def _format_keyword_matches(keywords: Sequence[str]) -> str:
    """Display matched keywords consistently in cart diagnostics."""
    return ", ".join(keywords) if keywords else NA_LABEL


def _variant_cart_usability(variant: CoffeeVariant) -> tuple[bool, str]:
    """Explain whether one variant can be selected for cart recommendations."""
    # Collect every blocker so cart-debug can explain the whole decision at once.
    reasons: list[str] = []
    if not variant.availability:
        reasons.append("unavailable")
    if variant.price_cents is None:
        reasons.append("missing price")
    if variant.weight_grams is None:
        reasons.append("missing weight")
    elif variant.weight_grams <= 0:
        reasons.append("non-positive weight")
    elif variant.weight_grams > MAX_CART_BAG_WEIGHT_GRAMS:
        reasons.append(f"over {MAX_CART_BAG_WEIGHT_GRAMS}g cap")
    if not is_retail_variant(variant.name):
        reasons.append("non-retail variant")

    # The boolean drives selection markers; the text is rendered in the table.
    if reasons:
        return False, ", ".join(reasons)
    return True, "usable"


@app.command(name="cart-debug")
def cart_debug(
    coffee_id: int,
    preferences: Path = preferences_file_option,
) -> None:
    """Explain why one cached coffee is or is not eligible for cart output."""
    # Start with the same preference parsing as ``gesha cart`` so diagnostics
    # describe the real cart command behavior.
    try:
        preference_config = _read_preferences_for_command(preferences)
    except ValueError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    # The database may not exist on a fresh checkout; initialize it before lookup.
    init_db()
    with get_session() as session:
        service = CoffeeService(session)
        coffee = service.get_coffee_by_id(coffee_id)
        if coffee is None:
            console.print(f"[red]Coffee with ID {coffee_id} not found.[/red]")
            raise typer.Exit(code=1)

        # Gather the same matching and variant-selection evidence used by carts.
        include_matches = matched_keywords(coffee, preference_config.keywords)
        exclude_matches = matched_keywords(coffee, preference_config.excluded_keywords)
        selected_variant = smallest_available_variant(coffee)
        cart_item = cart_item_for_coffee(
            coffee,
            preference_config.keywords,
            preference_config.excluded_keywords,
        )

        # Reasons explain hard skips; warnings explain usable recommendations
        # that may still be missing a pre-filled Shopify cart URL.
        reasons: list[str] = []
        warnings: list[str] = []
        if not coffee.availability:
            reasons.append("Coffee is marked unavailable; `gesha cart` only loads available coffees.")
        if exclude_matches:
            reasons.append(f"Coffee matches excluded keyword(s): {_format_keyword_matches(exclude_matches)}.")
        if not include_matches:
            reasons.append("Coffee does not match any include keyword.")
        if coffee.url is None:
            reasons.append("Coffee has no product URL.")
        if not coffee.variants:
            reasons.append("Coffee has no cached Shopify variants.")
        elif selected_variant is None:
            reasons.append(
                "No variant is available, retail-sized, priced, weighted, and within the "
                f"{MAX_CART_BAG_WEIGHT_GRAMS}g bag cap."
            )
        if cart_item is not None and cart_item.variant_id is None:
            warnings.append("Selected variant has no Shopify variant ID, so a pre-filled cart link cannot be built.")

        is_cart_eligible = coffee.availability and cart_item is not None
        result = "[green]Included in cart recommendations[/green]" if is_cart_eligible else "[red]Skipped[/red]"

        # The summary table mirrors the high-level cart eligibility decision.
        console.print(f"[bold cyan]Cart debug for coffee #{coffee_id}[/bold cyan]")
        summary = Table(show_header=False)
        summary.add_row("Result", result)
        summary.add_row("Roaster", coffee.roaster.name)
        summary.add_row("Name", coffee.name)
        summary.add_row("Availability", "yes" if coffee.availability else "no")
        summary.add_row("Include matches", _format_keyword_matches(include_matches))
        summary.add_row("Exclude matches", _format_keyword_matches(exclude_matches))
        summary.add_row("URL", coffee.url or NA_LABEL)
        if selected_variant is not None:
            summary.add_row(
                "Selected variant",
                (
                    f"{selected_variant.name} / {selected_variant.bag_size or NA_LABEL} / "
                    f"{price_display(selected_variant.price_cents)} / {selected_variant.weight_grams}g"
                ),
            )
        else:
            summary.add_row("Selected variant", NA_LABEL)
        console.print(summary)

        # Keep skip explanations separate from the data table for quick scanning.
        if reasons:
            console.print("[bold]Skip reason(s):[/bold]")
            for reason in reasons:
                console.print(f" - {reason}")
        else:
            console.print("[green]No skip reasons found.[/green]")

        if warnings:
            console.print("[bold yellow]Warning(s):[/bold yellow]")
            for warning in warnings:
                console.print(f" - {warning}")

        # Variant-by-variant diagnostics show why the selected variant won, or
        # why no variant was eligible.
        variants = Table(title="Cached variants", show_header=True, header_style="bold magenta")
        variants.add_column("Selected")
        variants.add_column("Variant")
        variants.add_column("Available")
        variants.add_column("Weight", justify="right")
        variants.add_column("Price", justify="right")
        variants.add_column("Cart status")
        for variant in coffee.variants:
            _, status = _variant_cart_usability(variant)
            variants.add_row(
                "yes" if selected_variant is variant else "",
                variant.name,
                "yes" if variant.availability else "no",
                f"{variant.weight_grams}g" if variant.weight_grams is not None else NA_LABEL,
                price_display(variant.price_cents),
                status,
            )
        console.print(variants)


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
        preference_config = _read_preferences_for_command(preferences)

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

    # Resolve through the scraper registry so cart all includes every supported
    # roaster, even before a shipping policy has been configured for it.
    selected_roasters = _selected_cart_roaster_names(source)
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

            candidates = recommend_carts(
                items,
                threshold_cents,
                keyword_priority=preference_config.keywords,
            )

            console.print(f"\n[bold cyan]{roaster_name}[/bold cyan]")
            console.print(f"Estimated free-shipping threshold: {price_display(threshold_cents)} ({threshold_source})")
            if policy_url:
                console.print(f"Policy: [link={policy_url}]{policy_url}[/link]")

            if not candidates:
                console.print(
                    "[yellow]No cached coffees match the current keywords and exclusions with usable variant data. "
                    "A fresh scrape may be needed to populate variant weights and prices.[/yellow]"
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

        # Fail before making network requests if there is no cached target.
        if coffee is None:
            console.print(f"[red]Coffee with ID {coffee_id} not found.[/red]")
            raise typer.Exit(code=1)

        # Older rows or manual fixtures can lack URLs, which makes raw capture impossible.
        if not coffee.url:
            console.print(f"[red]Coffee with ID {coffee_id} has no URL to debug.[/red]")
            raise typer.Exit(code=1)

        # One debug file contains both JSON and HTML so parser fixtures can be
        # derived from a single capture when a roaster changes its page shape.
        output_path = DEBUG_DIR / f"debug_{coffee_id}.txt"
        output_path.parent.mkdir(exist_ok=True)
        output: list[str] = [f"=== PRODUCT URL ===\n{coffee.url}\n\n"]
        scraper = _scraper_for_roaster_name(coffee.roaster.name)
        transport = cast(Any, scraper.session if scraper is not None else requests)

        # Capture a Shopify-style JSON response when supported; a missing JSON
        # endpoint is tolerated because non-Shopify records are also debuggable.
        json_url = f"{coffee.url}.js" if not coffee.url.endswith(".js") else coffee.url
        json_headers = None
        if scraper is not None:
            json_headers = transport.headers.copy()
            json_headers["Referer"] = coffee.url
        res_json = transport.get(json_url, headers=json_headers, timeout=15)
        if res_json.status_code == 200:
            output.append("=== RAW JSON DATA ===\n")
            output.append(res_json.text)
            output.append("\n\n")

        # The HTML response is always included because each parser may depend
        # on selectors or embedded page payloads not represented in JSON.
        res_html = transport.get(coffee.url, timeout=15)
        res_html.raise_for_status()
        output.append("=== RAW HTML DATA ===\n")
        output.append(res_html.text)

        output_path.write_text("".join(output), encoding="utf-8")

        console.print(f"[green]Full raw data dumped to {output_path}[/green]")


@app.command(name="fix-tasting-notes")
def fix_tasting_notes(
    source: str = typer_argument(
        ...,
        help="The roaster whose missing tasting notes should be diagnosed.",
    ),
    search: str = tasting_notes_debug_search_option,
    limit: int = tasting_notes_debug_limit_option,
) -> None:
    """Collect raw artifacts for cached coffees missing tasting notes."""
    # This command gathers evidence for a scraper fix; it does not edit parser
    # code or the database because tasting-note extraction needs source-specific review.
    if source == "all" or source not in supported_sources():
        valid_sources = sorted([name for name in supported_sources() if name != "all"])
        console.print(f"[red]Error: '{source}' is not a supported single roaster for tasting-note debugging.[/red]")
        console.print("\n[bold]Available roasters:[/bold]")
        for valid_source in valid_sources:
            console.print(f" - {valid_source}")
        raise typer.Exit(code=1)

    try:
        # Compile once before network/database work so an invalid regex fails fast.
        pattern = re.compile(search, flags=re.IGNORECASE)
    except re.error as exc:
        console.print(f"[red]Error: invalid --search regex: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    # First capture the batch feed, because missing notes often start there.
    collection_json(source, output_dir=DEBUG_DIR)
    collection_path = DEBUG_DIR / f"{source}.json"
    if collection_path.exists():
        _print_debug_matches(collection_path, pattern)

    scraper = get_scraper(source)
    init_db()
    with get_session() as session:
        service = CoffeeService(session)

        # Use the display roaster name from the scraper so source aliases and
        # cached database rows stay aligned.
        coffees = service.list_coffees(roaster_name=scraper.ROASTER_NAME)

        if not coffees:
            console.print(
                f"[yellow]No cached coffees found for {scraper.ROASTER_NAME}. Run `gesha scrape {source}` first.[/yellow]"
            )
            return

        # Only products with no notes and a URL can help diagnose extraction gaps.
        missing_notes = [
            coffee for coffee in coffees if coffee.id is not None and coffee.url and not coffee.tasting_notes
        ]
        if not missing_notes:
            console.print(f"[green]No cached {scraper.ROASTER_NAME} coffees are missing tasting notes.[/green]")
            return

        console.print(
            f"[yellow]{len(missing_notes)} cached {scraper.ROASTER_NAME} coffees are missing tasting notes.[/yellow]"
        )
        # Copy IDs out of the session before calling debug(), which opens its own
        # short read session and writes the product artifacts.
        debug_ids = [coffee.id for coffee in missing_notes[:limit] if coffee.id is not None]

    for coffee_id in debug_ids:
        # Product debug files include both Shopify .js and rendered HTML; the
        # HTML side is usually where theme-specific note selectors are discovered.
        debug(coffee_id)
        product_debug_path = DEBUG_DIR / f"debug_{coffee_id}.txt"
        if product_debug_path.exists():
            _print_debug_matches(product_debug_path, pattern)

    if len(debug_ids) < len(missing_notes):
        console.print(
            f"[yellow]Stopped after {len(debug_ids)} product dumps because --limit is {limit}. "
            "Increase --limit to inspect more cached products.[/yellow]"
        )

    console.print(
        "[blue]If matches appear in product debug files but not in parsed output, add product-page hydration "
        "or a source-specific tasting-note parser for this roaster.[/blue]"
    )


@app.command(name="test")
def test_command() -> None:
    """Run the project test suite through pytest."""
    console.print("[blue]Running tests...[/blue]")

    # Delegate to the active Python executable so the current venv is used.
    result = subprocess.run([sys.executable, "-m", "pytest"], check=False)
    raise typer.Exit(code=result.returncode)


if __name__ == "__main__":
    app()
