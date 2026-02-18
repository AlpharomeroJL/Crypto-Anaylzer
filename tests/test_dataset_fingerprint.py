"""Tests for crypto_analyzer.dataset fingerprinting."""
import sqlite3
import sys
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.dataset import (
    DatasetFingerprint,
    TableSummary,
    compute_dataset_fingerprint,
    dataset_id_from_fingerprint,
    get_dataset_id,
)


@pytest.fixture
def tmp_db(tmp_path):
    """Create a minimal SQLite DB with a snapshots table."""
    db = str(tmp_path / "test.sqlite")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE sol_monitor_snapshots "
            "(id INTEGER PRIMARY KEY, ts_utc TEXT, chain_id TEXT, pair_address TEXT, dex_price_usd REAL)"
        )
        conn.execute(
            "INSERT INTO sol_monitor_snapshots (ts_utc, chain_id, pair_address, dex_price_usd) "
            "VALUES ('2026-01-01T00:00:00', 'solana', 'abc123', 1.5)"
        )
        conn.execute(
            "INSERT INTO sol_monitor_snapshots (ts_utc, chain_id, pair_address, dex_price_usd) "
            "VALUES ('2026-01-02T00:00:00', 'solana', 'abc123', 2.0)"
        )
        conn.commit()
    return db


def test_fingerprint_row_count_and_ts(tmp_db):
    fp = compute_dataset_fingerprint(tmp_db)
    snap = [t for t in fp.tables if t.table == "sol_monitor_snapshots"]
    assert len(snap) == 1
    assert snap[0].row_count == 2
    assert snap[0].min_ts == "2026-01-01T00:00:00"
    assert snap[0].max_ts == "2026-01-02T00:00:00"


def test_dataset_id_deterministic(tmp_db):
    id1 = get_dataset_id(tmp_db)
    id2 = get_dataset_id(tmp_db)
    assert id1 == id2
    assert len(id1) == 16


def test_missing_tables_no_crash(tmp_db):
    fp = compute_dataset_fingerprint(tmp_db, tables=["nonexistent_table", "sol_monitor_snapshots"])
    table_names = [t.table for t in fp.tables]
    assert "nonexistent_table" not in table_names
    assert "sol_monitor_snapshots" in table_names


def test_missing_db_no_crash(tmp_path):
    fp = compute_dataset_fingerprint(str(tmp_path / "nope.sqlite"))
    assert fp.tables == []
    did = dataset_id_from_fingerprint(fp)
    assert len(did) == 16


def test_different_data_different_id(tmp_path):
    db1 = str(tmp_path / "a.sqlite")
    db2 = str(tmp_path / "b.sqlite")
    with sqlite3.connect(db1) as conn:
        conn.execute("CREATE TABLE sol_monitor_snapshots (ts_utc TEXT, dex_price_usd REAL)")
        conn.execute("INSERT INTO sol_monitor_snapshots VALUES ('2026-01-01', 1.0)")
        conn.commit()
    with sqlite3.connect(db2) as conn:
        conn.execute("CREATE TABLE sol_monitor_snapshots (ts_utc TEXT, dex_price_usd REAL)")
        conn.execute("INSERT INTO sol_monitor_snapshots VALUES ('2026-01-01', 1.0)")
        conn.execute("INSERT INTO sol_monitor_snapshots VALUES ('2026-01-02', 2.0)")
        conn.commit()
    assert get_dataset_id(db1) != get_dataset_id(db2)
