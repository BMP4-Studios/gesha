"""Tests for CLI helpers that should stay independent of real subprocesses."""

from __future__ import annotations

from types import SimpleNamespace

import gesha.cli.main as cli_main
import pytest


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
