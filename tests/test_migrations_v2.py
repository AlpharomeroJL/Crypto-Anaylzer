"""Tests for versioned schema migrations (migrations_v2)."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.db.migrations_v2 import (
    MIGRATIONS,
    _max_applied_version,
    _schema_migrations_exists,
    run_migrations_v2,
)


def test_migrations_v2_on_empty_db_creates_tables_and_records():
    """New empty DB: run migrations -> schema_migrations populated, factor_* tables exist."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        assert _schema_migrations_exists(conn)
        max_ver = _max_applied_version(conn)
        assert max_ver == len(MIGRATIONS)
        cur = conn.execute("SELECT version, name FROM schema_migrations ORDER BY version")
        rows = cur.fetchall()
        assert len(rows) == len(MIGRATIONS)
        for i, (v, name) in enumerate(rows):
            assert v == i + 1
            assert isinstance(name, str) and len(name) > 0
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('factor_model_runs','factor_betas','residual_returns')"
        )
        tables = [r[0] for r in cur.fetchall()]
        assert "factor_model_runs" in tables
        assert "factor_betas" in tables
        assert "residual_returns" in tables
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)


def test_migrations_v2_rerun_idempotent():
    """Rerun migrations -> no duplicate rows, same max version."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        max_before = _max_applied_version(conn)
        cur = conn.execute("SELECT COUNT(*) FROM schema_migrations")
        count_before = cur.fetchone()[0]
        conn.close()

        conn2 = sqlite3.connect(path)
        run_migrations_v2(conn2, path)
        max_after = _max_applied_version(conn2)
        cur = conn2.execute("SELECT COUNT(*) FROM schema_migrations")
        count_after = cur.fetchone()[0]
        conn2.close()

        assert max_after == max_before
        assert count_after == count_before
    finally:
        Path(path).unlink(missing_ok=True)


def test_migrations_v2_in_memory_no_backup():
    """In-memory DB: run_migrations_v2 without path does not fail (no backup)."""
    conn = sqlite3.connect(":memory:")
    run_migrations(conn, None)
    assert _max_applied_version(conn) == len(MIGRATIONS)
    conn.close()


def test_migrations_v2_failure_restores_backup():
    """When a migration fails, backup is restored and DB contents unchanged."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        # Insert a row so we can verify DB contents after restore (not just version)
        conn.execute(
            "INSERT INTO factor_model_runs (factor_run_id, created_at_utc, dataset_id, freq, window_bars, min_obs, factors_json, estimator) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("fctr_test_restore", "2026-02-19T12:00:00Z", "ds1", "1h", 24, 12, "[]", "rolling_ols"),
        )
        conn.commit()
        cur = conn.execute("SELECT COUNT(*) FROM schema_migrations")
        schema_count_before = cur.fetchone()[0]
        cur = conn.execute("SELECT COUNT(*) FROM factor_model_runs WHERE factor_run_id = ?", ("fctr_test_restore",))
        run_count_before = cur.fetchone()[0]
        conn.close()

        from crypto_analyzer.db import migrations_v2 as m2

        original_migrations = m2.MIGRATIONS.copy()

        def failing_fn(_conn):
            raise RuntimeError("simulated failure")

        m2.MIGRATIONS = list(original_migrations) + [(99, "failing_migration", failing_fn)]

        try:
            conn2 = sqlite3.connect(path)
            with pytest.raises(RuntimeError, match="simulated failure"):
                run_migrations_v2(conn2, path)
            conn2.close()
            conn3 = sqlite3.connect(path)
            assert _max_applied_version(conn3) == len(original_migrations)
            cur = conn3.execute("SELECT COUNT(*) FROM schema_migrations")
            assert cur.fetchone()[0] == schema_count_before
            cur = conn3.execute(
                "SELECT COUNT(*) FROM factor_model_runs WHERE factor_run_id = ?", ("fctr_test_restore",)
            )
            assert cur.fetchone()[0] == run_count_before
            conn3.close()
        finally:
            m2.MIGRATIONS = original_migrations
    finally:
        Path(path).unlink(missing_ok=True)
