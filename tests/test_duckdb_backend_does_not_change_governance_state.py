"""Phase 3.5 A7: DuckDB backend does not alter SQLite governance/lineage; lineage always written to SQLite conn."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.db.migrations_phase3 import run_migrations_phase3
from crypto_analyzer.store.duckdb_backend import DuckDBBackend
from crypto_analyzer.store.sqlite_session import sqlite_conn


def test_lineage_writes_go_to_sqlite_conn_not_duckdb():
    """write_artifact_lineage uses the provided SQLite conn only; DuckDB is never written for lineage/governance."""
    with tempfile.TemporaryDirectory() as tmp:
        sqlite_path = Path(tmp) / "gov.sqlite"
        with sqlite_conn(sqlite_path) as conn:
            run_migrations(conn, str(sqlite_path))
            run_migrations_phase3(conn, str(sqlite_path))
        backend = DuckDBBackend(duckdb_path=Path(tmp) / "analytics.duckdb")
        with sqlite_conn(sqlite_path) as conn:
            backend.write_artifact_lineage(
                conn,
                artifact_id="a" * 64,
                run_key="rk",
                dataset_id_v2="ds",
                artifact_type="manifest",
                sha256="a" * 64,
                created_utc="2026-02-22T00:00:00Z",
            )
            cur = conn.execute("SELECT COUNT(*) FROM artifact_lineage")
            assert cur.fetchone()[0] == 1


def test_switching_backend_does_not_alter_governance_tables():
    """Using DuckDB for read_table does not create or modify governance tables in SQLite."""
    duckdb = pytest.importorskip("duckdb")
    with tempfile.TemporaryDirectory() as tmp:
        sqlite_path = Path(tmp) / "gov.sqlite"
        with sqlite_conn(sqlite_path) as conn:
            run_migrations(conn, str(sqlite_path))
            run_migrations_phase3(conn, str(sqlite_path))
            cur = conn.execute("SELECT COUNT(*) FROM promotion_candidates")
            count_before = cur.fetchone()[0]
        duck_path = Path(tmp) / "a.duckdb"
        with duckdb.connect(str(duck_path)) as dconn:
            dconn.execute("CREATE TABLE t (x INT)")
            dconn.execute("INSERT INTO t VALUES (1)")
        backend = DuckDBBackend(duckdb_path=duck_path)
        backend.read_table("t", db_path=duck_path)
        with sqlite_conn(sqlite_path) as conn:
            cur = conn.execute("SELECT COUNT(*) FROM promotion_candidates")
            count_after = cur.fetchone()[0]
        assert count_after == count_before
