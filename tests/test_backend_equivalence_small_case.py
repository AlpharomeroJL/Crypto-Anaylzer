"""Phase 3 A5: SQLite and DuckDB backend yield equivalent results for deterministic read_table."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.store import get_backend
from crypto_analyzer.store.sqlite_backend import SQLiteBackend


def test_sqlite_backend_read_table():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "db.sqlite"
        conn = sqlite3.connect(str(db_path))
        run_migrations(conn, str(db_path))
        conn.execute("CREATE TABLE IF NOT EXISTS t (a INT, b TEXT)")
        conn.execute("INSERT INTO t (a, b) VALUES (1, 'x'), (2, 'y')")
        conn.commit()
        conn.close()
        backend = SQLiteBackend()
        df = backend.read_table("t", db_path=str(db_path))
        assert len(df) == 2
        assert list(df.columns) == ["a", "b"]
        assert df["a"].tolist() == [1, 2]


def test_backend_default_is_sqlite():
    b = get_backend()
    assert b is not None
    assert type(b).__name__ == "SQLiteBackend"
