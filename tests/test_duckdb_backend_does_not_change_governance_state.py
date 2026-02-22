"""Phase 3 A5: Using DuckDB backend for read_table does not alter SQLite governance/lineage state."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.db.migrations_phase3 import run_migrations_phase3
from crypto_analyzer.store.duckdb_backend import DuckDBBackend


def test_lineage_writes_go_to_sqlite_conn_not_duckdb():
    """write_artifact_lineage and write_artifact_edge use the provided conn (SQLite); DuckDB is never written for governance."""
    with tempfile.TemporaryDirectory() as tmp:
        sqlite_path = Path(tmp) / "gov.sqlite"
        conn = sqlite3.connect(str(sqlite_path))
        try:
            run_migrations(conn, str(sqlite_path))
            run_migrations_phase3(conn, str(sqlite_path))
            backend = DuckDBBackend(duckdb_path=Path(tmp) / "analytics.duckdb")
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
        finally:
            conn.close()
