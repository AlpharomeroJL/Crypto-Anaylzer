"""
Tests for read_api: context manager, pragmas, loaders against a temporary SQLite DB.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from crypto_analyzer.read_api import (
    _with_conn,
    load_latest_universe_allowlist,
    load_spot_snapshots_recent,
    load_universe_allowlist_stats,
    load_universe_churn_verification,
)


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary SQLite DB with migrations applied (spot + universe tables)."""
    db_path = str(tmp_path / "read_api_test.sqlite")
    with _with_conn(db_path):
        pass  # migrations applied on first use
    return db_path


def test_with_conn_is_context_manager():
    """_with_conn is a real context manager (yields connection, closes on exit)."""
    with _with_conn(":memory:") as conn:
        assert conn is not None
        cur = conn.execute("SELECT 1")
        assert cur.fetchone() == (1,)
    # Connection closed; using it would raise
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_with_conn_applies_pragmas(temp_db):
    """Connection has safe pragmas: foreign_keys=ON, journal_mode=WAL, busy_timeout set."""
    with _with_conn(temp_db) as conn:
        cur = conn.execute("PRAGMA foreign_keys")
        assert cur.fetchone()[0] == 1
        cur = conn.execute("PRAGMA journal_mode")
        assert cur.fetchone()[0].upper() == "WAL"
        cur = conn.execute("PRAGMA busy_timeout")
        assert cur.fetchone()[0] >= 0


def test_load_spot_snapshots_recent_empty(temp_db):
    """Empty DB returns empty DataFrame with expected columns."""
    df = load_spot_snapshots_recent(temp_db, limit=15)
    assert isinstance(df, pd.DataFrame)
    assert df.empty
    expected = {"ts_utc", "symbol", "spot_price_usd", "spot_source", "provider_name", "fetch_status"}
    assert set(df.columns) >= expected or df.empty


def test_load_spot_snapshots_recent_with_rows(temp_db):
    """With rows, returns correct columns and limit."""
    with sqlite3.connect(temp_db) as conn:
        conn.execute(
            "INSERT INTO spot_price_snapshots (ts_utc, symbol, spot_price_usd) VALUES (?, ?, ?)",
            ("2025-01-01 12:00:00", "BTC", 50000.0),
        )
        conn.execute(
            "INSERT INTO spot_price_snapshots (ts_utc, symbol, spot_price_usd) VALUES (?, ?, ?)",
            ("2025-01-01 13:00:00", "ETH", 3000.0),
        )
        conn.commit()
    df = load_spot_snapshots_recent(temp_db, limit=5)
    assert len(df) <= 5
    assert "ts_utc" in df.columns and "symbol" in df.columns and "spot_price_usd" in df.columns
    assert set(df["symbol"].tolist()) <= {"BTC", "ETH"}


def test_load_latest_universe_allowlist_empty(temp_db):
    """Empty universe_allowlist returns empty DataFrame."""
    df = load_latest_universe_allowlist(temp_db, limit=20)
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_load_latest_universe_allowlist_with_rows(temp_db):
    """With allowlist rows, returns expected columns."""
    with sqlite3.connect(temp_db) as conn:
        conn.execute(
            """INSERT INTO universe_allowlist (ts_utc, chain_id, pair_address, label, liquidity_usd, vol_h24, source)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("2025-01-01 00:00:00", "solana", "addr1", "SOL/USDC", 1e6, 5e5, "test"),
        )
        conn.commit()
    df = load_latest_universe_allowlist(temp_db, limit=20)
    assert not df.empty
    assert list(df.columns) == ["label", "chain_id", "pair_address", "liquidity_usd", "vol_h24", "source"]
    assert df["label"].iloc[0] == "SOL/USDC"


def test_load_universe_allowlist_stats_empty(temp_db):
    """Empty DB returns (None, 0, 0)."""
    latest_ts, size, n_refreshes = load_universe_allowlist_stats(temp_db)
    assert latest_ts is None
    assert size == 0
    assert n_refreshes == 0


def test_load_universe_allowlist_stats_with_data(temp_db):
    """With one ts_utc, returns that ts and count 1."""
    with sqlite3.connect(temp_db) as conn:
        conn.execute(
            "INSERT INTO universe_allowlist (ts_utc, chain_id, pair_address) VALUES (?, ?, ?)",
            ("2025-01-01 00:00:00", "solana", "addr1"),
        )
        conn.commit()
    latest_ts, size, n_refreshes = load_universe_allowlist_stats(temp_db)
    assert latest_ts == "2025-01-01 00:00:00"
    assert size == 1
    assert n_refreshes == 1


def test_load_universe_churn_verification_empty(temp_db):
    """Empty churn returns empty DataFrames."""
    allowlist_df, churn_df = load_universe_churn_verification(temp_db)
    assert allowlist_df.empty
    assert churn_df.empty


def test_read_api_raises_on_connection_error(monkeypatch):
    """Policy: exceptions propagate to caller (no silent empty return)."""
    import crypto_analyzer.read_api as read_api

    def failing_conn(db_path):
        import contextlib

        @contextlib.contextmanager
        def cm():
            raise sqlite3.OperationalError("no such table: fake")

        return cm()

    monkeypatch.setattr(read_api, "_with_conn", failing_conn)
    with pytest.raises(sqlite3.OperationalError):
        read_api.load_spot_snapshots_recent("/any/path.sqlite", limit=1)
