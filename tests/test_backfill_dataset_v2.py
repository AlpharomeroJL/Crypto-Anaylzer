"""
Phase 1 verification: backfill_dataset_id_v2 populates dataset_id_v2, algo, mode; updates experiments.
"""

from __future__ import annotations

import sqlite3

from crypto_analyzer.dataset_v2 import backfill_dataset_id_v2, get_dataset_id_v2
from crypto_analyzer.experiments import ensure_experiment_tables


def test_backfill_populates_dataset_metadata_and_experiments(tmp_path):
    """Run backfill on DB with in-scope table and experiments: dataset_id_v2 in dataset_metadata; experiments rows updated."""
    db = str(tmp_path / "backfill.sqlite")
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE spot_price_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_utc TEXT NOT NULL,
                symbol TEXT NOT NULL,
                spot_price_usd REAL NOT NULL,
                spot_source TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO spot_price_snapshots (ts_utc, symbol, spot_price_usd, spot_source) VALUES (?, ?, ?, ?)",
            ("2026-01-01T00:00:00", "BTC", 50000.0, "cex"),
        )
        conn.commit()
    expected_id, expected_meta = get_dataset_id_v2(db, mode="STRICT")

    with sqlite3.connect(db) as conn:
        ensure_experiment_tables(conn)
        conn.execute(
            "INSERT INTO experiments (run_id, ts_utc) VALUES (?, ?)",
            ("run_old", "2026-01-01T00:00:00"),
        )
        conn.commit()

    got_id, got_meta = backfill_dataset_id_v2(db)
    assert got_id == expected_id
    assert got_meta.get("dataset_hash_algo") == "sqlite_logical_v2"
    assert got_meta.get("dataset_hash_mode") == "STRICT"

    with sqlite3.connect(db) as conn:
        cur = conn.execute("SELECT key, value FROM dataset_metadata WHERE key IN ('dataset_id_v2','dataset_hash_algo','dataset_hash_mode')")
        rows = {r[0]: r[1] for r in cur.fetchall()}
    assert rows.get("dataset_id_v2") == expected_id
    assert rows.get("dataset_hash_algo") == "sqlite_logical_v2"
    assert rows.get("dataset_hash_mode") == "STRICT"

    with sqlite3.connect(db) as conn:
        cur = conn.execute("SELECT dataset_id_v2, dataset_hash_algo, dataset_hash_mode FROM experiments WHERE run_id = ?", ("run_old",))
        row = cur.fetchone()
    assert row is not None
    assert row[0] == expected_id
    assert row[1] == "sqlite_logical_v2"
    assert row[2] == "STRICT"
