"""
Phase 3.5 A3: DB connection lifecycle — context managers, guaranteed close, Windows-safe cleanup.
Temp DB must be deletable immediately after connection close.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from crypto_analyzer.store.sqlite_session import sqlite_conn


def test_sqlite_conn_closes_and_file_deletable():
    """After exiting sqlite_conn context, connection is closed and file can be deleted (Windows)."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name
    try:
        with sqlite_conn(db_path) as conn:
            conn.execute("CREATE TABLE t (x INTEGER)")
            conn.commit()
        # Context exited; conn closed. On Windows, file must be deletable now.
        Path(db_path).unlink()
    except OSError as e:
        pytest.fail(f"DB file could not be deleted after close (Windows lock?): {e}")


def test_sqlite_conn_foreign_keys_on():
    """sqlite_conn enables PRAGMA foreign_keys=ON."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name
    try:
        with sqlite_conn(db_path) as conn:
            cur = conn.execute("PRAGMA foreign_keys")
            row = cur.fetchone()
            assert row is not None and row[0] == 1
    finally:
        Path(db_path).unlink(missing_ok=True)


def test_sqlite_conn_multiple_sequential():
    """Open and close multiple connections sequentially; file remains deletable."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name
    try:
        with sqlite_conn(db_path) as c1:
            c1.execute("CREATE TABLE IF NOT EXISTS t (x INT)")
            c1.commit()
        with sqlite_conn(db_path) as c2:
            c2.execute("INSERT INTO t (x) VALUES (1)")
            c2.commit()
        Path(db_path).unlink()
    except OSError as e:
        pytest.fail(f"DB file could not be deleted after sequential closes: {e}")
