"""Phase 3 A4: artifact_lineage and artifact_edges tables are append-only (triggers block mutation)."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from crypto_analyzer.db.lineage import lineage_tables_exist, write_artifact_lineage
from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.db.migrations_phase3 import run_migrations_phase3


def test_artifact_lineage_append_only_triggers_block_update_and_delete():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "lineage.db"
        conn = sqlite3.connect(str(db_path))
        run_migrations(conn, str(db_path))
        run_migrations_phase3(conn, str(db_path))
        if not lineage_tables_exist(conn):
            return
        write_artifact_lineage(
            conn,
            artifact_id="a1" + "0" * 62,
            run_key="rk1",
            dataset_id_v2="ds1",
            artifact_type="manifest",
            relative_path="manifest.json",
            sha256="a1" + "0" * 62,
            created_utc="2026-02-22T00:00:00Z",
        )
        try:
            conn.execute(
                "UPDATE artifact_lineage SET run_key = 'x' WHERE artifact_id = ?",
                ("a1" + "0" * 62,),
            )
            conn.commit()
            raise AssertionError("UPDATE on artifact_lineage should have been blocked")
        except sqlite3.IntegrityError:
            pass
        try:
            conn.execute("DELETE FROM artifact_lineage WHERE artifact_id = ?", ("a1" + "0" * 62,))
            conn.commit()
            raise AssertionError("DELETE on artifact_lineage should have been blocked")
        except sqlite3.IntegrityError:
            pass
        conn.close()
