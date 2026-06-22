"""Tests for CLI helpers that should stay independent of real subprocesses."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import gesha.cli.main as cli_main
import pytest
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


def test_rebuild_backs_up_resets_and_scrapes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """The rebuild command backs up the current DB before replacing it."""
    db_path = tmp_path / "gesha.db"
    backup_dir = tmp_path / "backups"

    with sqlite3.connect(str(db_path)) as connection:
        connection.execute("CREATE TABLE marker (id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO marker (id) VALUES (1)")

    for sidecar_name in ("gesha.db-wal", "gesha.db-shm", "gesha.db-journal"):
        (tmp_path / sidecar_name).write_text("sidecar", encoding="utf-8")

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
    with sqlite3.connect(str(backups[0])) as backup_connection:
        marker_count = backup_connection.execute("SELECT COUNT(*) FROM marker").fetchone()[0]
    assert marker_count == 1
