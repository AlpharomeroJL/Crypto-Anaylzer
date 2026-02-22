"""
Phase 1 verification: dataset hash v2 is logical (content-addressed).
- One row value change in a hashed table -> dataset_id_v2 changes.
- VACUUM without data change -> dataset_id_v2 unchanged.
- Tables excluded from scope do not affect the hash.
- FAST_DEV writes dataset_hash_mode='FAST_DEV' (gatekeeper blocks; see test_promotion_gating).
"""

from __future__ import annotations

import sqlite3

from crypto_analyzer.dataset_v2 import get_dataset_id_v2


def _db_with_spot_table(path: str, rows: list[tuple]) -> None:
    """Create DB with spot_price_snapshots (in scope) and optional rows."""
    with sqlite3.connect(path) as conn:
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
        for r in rows:
            conn.execute(
                "INSERT INTO spot_price_snapshots (ts_utc, symbol, spot_price_usd, spot_source) VALUES (?, ?, ?, ?)",
                r,
            )
        conn.commit()


def test_one_row_value_change_changes_dataset_id_v2(tmp_path):
    """Change one row value in a hashed table -> dataset_id_v2 changes."""
    db = str(tmp_path / "a.sqlite")
    _db_with_spot_table(db, [("2026-01-01T00:00:00", "BTC", 50000.0, "cex")])
    id_before, _ = get_dataset_id_v2(db, mode="STRICT")

    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE spot_price_snapshots SET spot_price_usd = ? WHERE symbol = ?",
            (50001.0, "BTC"),
        )
        conn.commit()
    id_after, _ = get_dataset_id_v2(db, mode="STRICT")
    assert id_before != id_after


def test_vacuum_without_data_change_preserves_dataset_id_v2(tmp_path):
    """VACUUM without data change -> dataset_id_v2 does not change."""
    db = str(tmp_path / "v.sqlite")
    _db_with_spot_table(db, [("2026-01-01T00:00:00", "BTC", 50000.0, "cex")])
    id_before, _ = get_dataset_id_v2(db, mode="STRICT")

    with sqlite3.connect(db) as conn:
        conn.execute("VACUUM")
        conn.commit()
    id_after, _ = get_dataset_id_v2(db, mode="STRICT")
    assert id_before == id_after


def test_excluded_tables_do_not_affect_hash(tmp_path):
    """Data in tables excluded from scope (e.g. experiments) does not affect dataset_id_v2."""
    db = str(tmp_path / "ex.sqlite")
    _db_with_spot_table(db, [("2026-01-01T00:00:00", "BTC", 50000.0, "cex")])
    id_without_experiments, _ = get_dataset_id_v2(db, mode="STRICT")

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS experiments (
                run_id TEXT PRIMARY KEY, ts_utc TEXT NOT NULL, git_commit TEXT,
                spec_version TEXT, out_dir TEXT, notes TEXT, data_start TEXT, data_end TEXT,
                config_hash TEXT, env_fingerprint TEXT, hypothesis TEXT, tags_json TEXT,
                dataset_id TEXT, params_json TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO experiments (run_id, ts_utc) VALUES (?, ?)",
            ("run_xyz", "2026-02-01T12:00:00"),
        )
        conn.commit()
    id_with_experiments, _ = get_dataset_id_v2(db, mode="STRICT")
    assert id_without_experiments == id_with_experiments


def test_fast_dev_writes_dataset_hash_mode(tmp_path):
    """FAST_DEV mode writes dataset_hash_mode='FAST_DEV' in metadata."""
    db = str(tmp_path / "f.sqlite")
    _db_with_spot_table(db, [("2026-01-01T00:00:00", "BTC", 50000.0, "cex")])
    _, meta = get_dataset_id_v2(db, mode="FAST_DEV")
    assert meta.get("dataset_hash_mode") == "FAST_DEV"
    assert meta.get("dataset_hash_algo") == "sqlite_logical_v2"


def test_strict_mode_metadata(tmp_path):
    """STRICT mode writes dataset_hash_mode='STRICT' and scope/excludes."""
    db = str(tmp_path / "s.sqlite")
    _db_with_spot_table(db, [("2026-01-01T00:00:00", "BTC", 50000.0, "cex")])
    _, meta = get_dataset_id_v2(db, mode="STRICT")
    assert meta.get("dataset_hash_mode") == "STRICT"
    assert "dataset_hash_scope" in meta
    assert "dataset_hash_excludes" in meta
    assert "spot_price_snapshots" in (meta.get("dataset_hash_scope") or [])
