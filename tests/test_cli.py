"""Tests for CLI helpers that should stay independent of real subprocesses."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import gesha.cli.main as cli_main
import pytest
from gesha.db.models import Coffee, CoffeeVariant, Roaster, TastingNote
from gesha.scrapers.shopify_scraper import TrafficScraper


class FakeCollectionResponse:
    """Small HTTP response fixture for collection JSON downloads."""

    status_code = 200
    text = '{"products":[{"title":"Milkshake Espresso"}]}'

    def raise_for_status(self) -> None:
        """Mirror the successful response method used by the command."""
        return None


class FakeCollectionSession:
    """Capture the collection JSON URL without making a real network request."""

    def __init__(self) -> None:
        """Track requested URLs for assertions."""
        self.calls: list[tuple[str, int]] = []

    def get(self, url: str, timeout: int) -> FakeCollectionResponse:
        """Return a deterministic collection JSON response."""
        self.calls.append((url, timeout))
        return FakeCollectionResponse()


class FakeSession:
    """Context manager fixture used by CLI commands that open a DB session."""

    def __enter__(self) -> "FakeSession":
        """Return the fake session object expected by CoffeeService."""
        return self

    def __exit__(self, *args: object) -> None:
        """Close the fake session context."""
        return None


class FakeDebugResponse:
    """Small HTTP response fixture for the debug command."""

    def __init__(self, text: str) -> None:
        """Store response text with an OK status."""
        self.status_code = 200
        self.text = text

    def raise_for_status(self) -> None:
        """Mirror the successful response method used by the command."""
        return None


class FakeDebugTransport:
    """Capture debug HTTP requests made through a scraper session."""

    def __init__(self) -> None:
        """Track requests and expose browser-like headers."""
        self.headers = {"User-Agent": "fake-browser"}
        self.calls: list[tuple[str, dict[str, str] | None, int]] = []

    def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: int = 15,
    ) -> FakeDebugResponse:
        """Return deterministic JSON or HTML debug responses."""
        self.calls.append((url, headers, timeout))
        if url.endswith(".js"):
            return FakeDebugResponse('{"title":"Debug Coffee"}')
        return FakeDebugResponse("<html>Debug Coffee</html>")


def test_test_command_runs_pytest_with_active_python(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ``gesha test`` command delegates to pytest and returns its exit code."""
    calls: list[tuple[list[str], bool]] = []

    def fake_run(args: list[str], check: bool) -> SimpleNamespace:
        """Capture subprocess arguments without starting another test process."""
        calls.append((args, check))
        return SimpleNamespace(returncode=7)

    # Avoid recursively starting pytest from inside pytest.
    monkeypatch.setattr(cli_main.subprocess, "run", fake_run)

    # Typer commands signal process exit by raising ``typer.Exit``.
    with pytest.raises(cli_main.typer.Exit) as exc_info:
        cli_main.test_command()

    assert calls == [([cli_main.sys.executable, "-m", "pytest"], False)]
    assert exc_info.value.exit_code == 7


def test_collection_json_command_writes_roaster_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """The json command saves a pretty Shopify feed as <source>.json."""
    # Replace registry lookup with one scraper whose session is fully controlled.
    scraper = TrafficScraper()
    fake_session = FakeCollectionSession()
    monkeypatch.setattr(scraper, "session", fake_session)
    monkeypatch.setattr(cli_main, "get_scraper", lambda source: scraper)

    cli_main.collection_json("traffic", output_dir=tmp_path)

    assert fake_session.calls == [
        ("https://www.trafficcoffee.com/collections/coffee/products.json?limit=250&page=1", 15)
    ]
    assert (tmp_path / "traffic.json").read_text(encoding="utf-8") == (
        '{\n  "products": [\n    {\n      "title": "Milkshake Espresso"\n    }\n  ]\n}\n'
    )


def test_fix_tasting_notes_downloads_collection_and_missing_product_debug(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """The tasting-note diagnostic command gathers the usual debug artifacts."""
    scraper = TrafficScraper()
    fake_session = FakeCollectionSession()
    roaster = Roaster(name="Traffic Coffee")
    missing_notes = Coffee(
        id=7,
        name="Missing Notes",
        url="https://example.test/products/missing-notes",
        roaster=roaster,
    )
    parsed_notes = Coffee(
        id=8,
        name="Parsed Notes",
        url="https://example.test/products/parsed-notes",
        roaster=roaster,
    )
    parsed_notes.tasting_notes.append(TastingNote(name="peach"))
    debug_calls: list[int] = []

    class FakeCoffeeService:
        """Return cached coffees without touching a real database."""

        def __init__(self, session: FakeSession) -> None:
            """Accept the fake session for API compatibility."""
            self.session = session

        def list_coffees(
            self,
            process: str | None = None,
            flavour: str | None = None,
            roaster_name: str | None = None,
            available: bool | None = None,
        ) -> list[Coffee]:
            """Return one coffee missing notes and one already parsed coffee."""
            assert roaster_name == "Traffic Coffee"
            return [missing_notes, parsed_notes]

    def fake_write_cached_raw_debug_data(coffee_id: int) -> Path:
        """Write the product debug file that the diagnostic command should scan."""
        debug_calls.append(coffee_id)
        cli_main.DEBUG_DIR.mkdir(exist_ok=True)
        debug_path = cli_main.DEBUG_DIR / f"debug_{coffee_id}.txt"
        debug_path.write_text(
            "=== RAW HTML DATA ===\nDebug Coffee tasting notes: Peach",
            encoding="utf-8",
        )
        return debug_path

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(scraper, "session", fake_session)
    monkeypatch.setattr(cli_main, "get_scraper", lambda source: scraper)
    monkeypatch.setattr(cli_main, "init_db", lambda: None)
    monkeypatch.setattr(cli_main, "get_session", lambda: FakeSession())
    monkeypatch.setattr(cli_main, "CoffeeService", FakeCoffeeService)
    monkeypatch.setattr(cli_main, "_write_cached_raw_debug_data", fake_write_cached_raw_debug_data)

    cli_main.fix_tasting_notes("traffic", search="Debug Coffee|tasting", limit=2)

    assert fake_session.calls == [
        ("https://www.trafficcoffee.com/collections/coffee/products.json?limit=250&page=1", 15)
    ]
    assert (tmp_path / "debug" / "traffic.json").exists()
    assert (tmp_path / "debug" / "debug_7.txt").exists()
    assert debug_calls == [7]


def test_rebuild_backs_up_resets_and_scrapes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """The rebuild command backs up the current DB before replacing it."""
    # Create a real SQLite file so the backup path exercises sqlite3.backup().
    db_path = tmp_path / "gesha.db"
    backup_dir = tmp_path / "backups"

    with closing(sqlite3.connect(str(db_path))) as connection:
        connection.execute("CREATE TABLE marker (id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO marker (id) VALUES (1)")
        connection.commit()

    # Sidecar files should disappear along with the primary database.
    for sidecar_name in ("gesha.db-wal", "gesha.db-shm", "gesha.db-journal"):
        (tmp_path / sidecar_name).write_text("sidecar", encoding="utf-8")

    # Stub schema creation and scraping so the test focuses on rebuild plumbing.
    calls: list[str] = []
    monkeypatch.setattr(cli_main, "DB_PATH", db_path)
    monkeypatch.setattr(cli_main, "init_db", lambda: calls.append("init"))
    monkeypatch.setattr(cli_main, "_refresh_catalog", lambda source: calls.append(f"scrape:{source}"))

    cli_main.rebuild(yes=True, backup_dir=backup_dir, no_scrape=False)

    assert calls == ["init", "scrape:all"]
    assert not db_path.exists()
    assert not (tmp_path / "gesha.db-wal").exists()
    assert not (tmp_path / "gesha.db-shm").exists()
    assert not (tmp_path / "gesha.db-journal").exists()

    backups = list(backup_dir.glob("gesha-*.db"))
    assert len(backups) == 1
    with closing(sqlite3.connect(str(backups[0]))) as backup_connection:
        marker_count = backup_connection.execute("SELECT COUNT(*) FROM marker").fetchone()[0]
    assert marker_count == 1


def test_debug_explains_unavailable_keyword_match(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A matching coffee can still be skipped when availability/variants fail."""
    # Preferences include both matches and exclusions so debug prints each path.
    preferences = tmp_path / "preferences.txt"
    preferences.write_text("gesha\ncoferment\n! decaf\n", encoding="utf-8")

    # The fixture coffee matches preferences but is unavailable at both product
    # and variant level, which should produce a skip explanation.
    coffee = Coffee(
        id=25,
        name="Colombia Gesha",
        availability=False,
        url="https://example.test/products/colombia-gesha",
        roaster=Roaster(name="Test Roaster"),
        tasting_notes=[TastingNote(name="pineapple")],
        variants=[
            CoffeeVariant(
                shopify_variant_id="variant-25",
                name="250g",
                price_cents=2800,
                bag_size="250g",
                weight_grams=250,
                availability=False,
            )
        ],
    )
    transport = FakeDebugTransport()

    class FakeCoffeeService:
        """Return the fixture coffee without touching a real database."""

        def __init__(self, session: FakeSession) -> None:
            """Accept the fake session for API compatibility."""
            self.session = session

        def get_coffee_by_id(self, coffee_id: int) -> Coffee | None:
            """Return the requested fixture coffee."""
            return coffee if coffee_id == 25 else None

    # Replace database access with the fixture service while keeping command code intact.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli_main, "init_db", lambda: None)
    monkeypatch.setattr(cli_main, "get_session", lambda: FakeSession())
    monkeypatch.setattr(cli_main, "CoffeeService", FakeCoffeeService)
    monkeypatch.setattr(
        cli_main,
        "get_scrapers",
        lambda source: [SimpleNamespace(ROASTER_NAME="Test Roaster", session=transport)],
    )

    cli_main.debug(25, preferences=preferences)

    output = capsys.readouterr().out
    assert "Skipped" in output
    assert "gesha" in output
    assert "Coffee is marked unavailable" in output
    assert "unavailable" in output
    assert (tmp_path / "debug" / "debug_25.txt").exists()


def test_refresh_catalog_continues_when_one_scraper_raises(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failed scraper future does not abort the whole refresh command."""

    class GoodScraper:
        """Fixture scraper that returns an empty but successful catalog."""

        SOURCE_NAME = "Good"
        ROASTER_NAME = "Good Roaster"

        def scrape(self) -> list[object]:
            """Return a successful empty scrape."""
            return []

    class BadScraper:
        """Fixture scraper that simulates a transport/parser crash."""

        SOURCE_NAME = "Bad"
        ROASTER_NAME = "Bad Roaster"

        def scrape(self) -> list[object]:
            """Raise like a real failed scraper can."""
            raise RuntimeError("boom")

    class FakeCoffeeService:
        """Minimal service used by _refresh_catalog."""

        def __init__(self, session: FakeSession) -> None:
            """Accept the fake session for API compatibility."""
            self.session = session

        def list_coffees(self, *args: object, **kwargs: object) -> list[object]:
            """Return no cached coffees for final rendering."""
            return []

        def create_or_update_coffee(self, coffee: object) -> None:
            """Record no-op imports."""
            return None

        def delete_stale_coffees(self, roaster_name: str, current_urls: list[str]) -> int:
            """Return no stale deletions."""
            return 0

    monkeypatch.setattr(cli_main, "init_db", lambda: None)
    monkeypatch.setattr(cli_main, "get_session", lambda: FakeSession())
    monkeypatch.setattr(cli_main, "CoffeeService", FakeCoffeeService)
    monkeypatch.setattr(cli_main, "supported_sources", lambda: ["all", "good", "bad"])
    monkeypatch.setattr(cli_main, "get_scrapers", lambda source: [GoodScraper(), BadScraper()])

    cli_main._refresh_catalog("all")

    output = capsys.readouterr().out
    assert "Failed Bad: boom" in output
    assert "Finished Good" in output


def test_scrape_serial_option_forces_one_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    """The public --serial flag maps to the same worker count as --workers 1."""
    calls: list[tuple[str, int | None]] = []

    def fake_refresh_catalog(source: str, workers: int | None = None) -> None:
        """Capture scrape orchestration arguments without network work."""
        calls.append((source, workers))

    monkeypatch.setattr(cli_main, "_refresh_catalog", fake_refresh_catalog)

    cli_main.scrape(source="all", workers=4, serial=True)

    assert calls == [("all", 1)]


def test_refresh_catalog_workers_one_runs_scrapers_in_source_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Serial refresh contacts one roaster at a time in registry order."""
    events: list[str] = []

    class FirstScraper:
        """First fixture scraper in source order."""

        SOURCE_NAME = "First"
        ROASTER_NAME = "First Roaster"

        def scrape(self) -> list[object]:
            """Record the serial execution order."""
            events.append("first")
            return []

    class SecondScraper:
        """Second fixture scraper in source order."""

        SOURCE_NAME = "Second"
        ROASTER_NAME = "Second Roaster"

        def scrape(self) -> list[object]:
            """Record the serial execution order."""
            events.append("second")
            return []

    class FakeCoffeeService:
        """Minimal service used by _refresh_catalog."""

        def __init__(self, session: FakeSession) -> None:
            """Accept the fake session for API compatibility."""
            self.session = session

        def list_coffees(self, *args: object, **kwargs: object) -> list[object]:
            """Return no cached coffees for final rendering."""
            return []

        def create_or_update_coffee(self, coffee: object) -> None:
            """Record no-op imports."""
            return None

        def delete_stale_coffees(self, roaster_name: str, current_urls: list[str]) -> int:
            """Return no stale deletions."""
            return 0

    monkeypatch.setattr(cli_main, "init_db", lambda: None)
    monkeypatch.setattr(cli_main, "get_session", lambda: FakeSession())
    monkeypatch.setattr(cli_main, "CoffeeService", FakeCoffeeService)
    monkeypatch.setattr(cli_main, "supported_sources", lambda: ["all", "first", "second"])
    monkeypatch.setattr(cli_main, "get_scrapers", lambda source: [FirstScraper(), SecondScraper()])

    cli_main._refresh_catalog("all", workers=1)

    assert events == ["first", "second"]


def test_cart_all_roasters_come_from_scraper_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """cart all follows supported scrapers, not the shipping policy keys."""
    monkeypatch.setattr(
        cli_main,
        "get_scrapers",
        lambda source: [
            SimpleNamespace(ROASTER_NAME="Registry Roaster A"),
            SimpleNamespace(ROASTER_NAME="Registry Roaster B"),
        ],
    )

    assert cli_main._selected_cart_roaster_names("all") == [
        "Registry Roaster A",
        "Registry Roaster B",
    ]


def test_debug_uses_scraper_transport(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Raw debug captures use the same scraper session as normal scraping."""
    transport = FakeDebugTransport()
    coffee = Coffee(
        id=7,
        name="Debug Coffee",
        url="https://example.test/products/debug-coffee",
        roaster=Roaster(name="Test Roaster"),
    )

    class FakeCoffeeService:
        """Return the fixture coffee without touching a real database."""

        def __init__(self, session: FakeSession) -> None:
            """Accept the fake session for API compatibility."""
            self.session = session

        def get_coffee_by_id(self, coffee_id: int) -> Coffee | None:
            """Return the requested fixture coffee."""
            return coffee if coffee_id == 7 else None

    fake_scraper = SimpleNamespace(ROASTER_NAME="Test Roaster", session=transport)

    def fail_plain_requests(*args: object, **kwargs: object) -> None:
        """Fail if debug falls back to plain requests for a known roaster."""
        raise AssertionError("plain requests should not be used")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli_main, "init_db", lambda: None)
    monkeypatch.setattr(cli_main, "get_session", lambda: FakeSession())
    monkeypatch.setattr(cli_main, "CoffeeService", FakeCoffeeService)
    monkeypatch.setattr(cli_main, "get_scrapers", lambda source: [fake_scraper])
    monkeypatch.setattr(cli_main.requests, "get", fail_plain_requests)

    cli_main.debug(7, preferences=cli_main.DEFAULT_PREFERENCES_PATH)

    assert transport.calls == [
        (
            "https://example.test/products/debug-coffee.js",
            {
                "User-Agent": "fake-browser",
                "Referer": "https://example.test/products/debug-coffee",
            },
            15,
        ),
        ("https://example.test/products/debug-coffee", None, 15),
    ]
    assert (tmp_path / "debug" / "debug_7.txt").read_text(encoding="utf-8") == (
        "=== PRODUCT URL ===\n"
        "https://example.test/products/debug-coffee\n\n"
        '=== RAW JSON DATA ===\n{"title":"Debug Coffee"}\n\n=== RAW HTML DATA ===\n<html>Debug Coffee</html>'
    )
