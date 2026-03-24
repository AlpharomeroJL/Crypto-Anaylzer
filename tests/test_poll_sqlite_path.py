"""Poll CLI resolves SQLite path the same way as the rest of the stack (config / env / --db)."""

from __future__ import annotations

from argparse import Namespace

from crypto_analyzer.cli import poll as poll_mod


def test_poll_sqlite_path_prefers_cli_db() -> None:
    assert poll_mod._poll_sqlite_path(Namespace(db="custom.sqlite")) == "custom.sqlite"


def test_poll_sqlite_path_uses_config(monkeypatch) -> None:
    monkeypatch.setattr(poll_mod, "config_sqlite_db_path", lambda: "from_config.sqlite")
    assert poll_mod._poll_sqlite_path(Namespace(db=None)) == "from_config.sqlite"
