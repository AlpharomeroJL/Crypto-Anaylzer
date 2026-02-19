"""Phase 3 migrations: not applied by default; apply only via run_migrations_phase3 when regimes enabled."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.db.migrations_phase3 import (
    MIGRATIONS_PHASE3,
    _max_applied_version_phase3,
    _schema_migrations_phase3_exists,
    run_migrations_phase3,
)


def test_default_run_migrations_does_not_create_phase3_tables():
    """run_migrations() must NOT create regime_runs, regime_states, or schema_migrations_phase3."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('regime_runs','regime_states','schema_migrations_phase3')"
        )
        phase3_tables = [r[0] for r in cur.fetchall()]
        assert "regime_runs" not in phase3_tables
        assert "regime_states" not in phase3_tables
        assert "schema_migrations_phase3" not in phase3_tables
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)


def test_run_migrations_phase3_creates_tables_and_records():
    """Explicit run_migrations_phase3(): regime_runs, regime_states, schema_migrations_phase3 exist."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        run_migrations_phase3(conn, path)
        assert _schema_migrations_phase3_exists(conn)
        assert _max_applied_version_phase3(conn) == len(MIGRATIONS_PHASE3)
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('regime_runs','regime_states')"
        )
        tables = [r[0] for r in cur.fetchall()]
        assert "regime_runs" in tables
        assert "regime_states" in tables
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)


def test_run_migrations_phase3_rerun_idempotent():
    """Rerun run_migrations_phase3 -> same version count, no duplicate migration rows."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        run_migrations_phase3(conn, path)
        max_before = _max_applied_version_phase3(conn)
        cur = conn.execute("SELECT COUNT(*) FROM schema_migrations_phase3")
        count_before = cur.fetchone()[0]
        conn.close()

        conn2 = sqlite3.connect(path)
        run_migrations_phase3(conn2, path)
        max_after = _max_applied_version_phase3(conn2)
        cur = conn2.execute("SELECT COUNT(*) FROM schema_migrations_phase3")
        count_after = cur.fetchone()[0]
        conn2.close()

        assert max_after == max_before
        assert count_after == count_before
    finally:
        Path(path).unlink(missing_ok=True)
