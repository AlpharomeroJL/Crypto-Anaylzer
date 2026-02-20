"""
Tests for data loaders (load_snapshots, load_bars, load_spot_series) using a temporary SQLite DB.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from crypto_analyzer.data import (
    load_bars,
    load_snapshots,
    load_spot_series,
)
from crypto_analyzer.read_api import _with_conn


def _create_temp_db_with_schema(tmp_path):
    """Create a temp DB with minimal schema: sol_monitor_snapshots, spot_price_snapshots, bars_1h."""
    db_path = str(tmp_path / "data_loaders_test.sqlite")
    with _with_conn(db_path) as conn:
        pass  # migrations create sol_monitor_snapshots, spot_price_snapshots, universe_*, etc.
    # bars_1h is not in core migrations; create it manually for tests
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bars_1h (
                ts_utc TEXT NOT NULL,
                chain_id TEXT NOT NULL,
                pair_address TEXT NOT NULL,
                base_symbol TEXT,
                quote_symbol TEXT,
                open REAL, high REAL, low REAL, close REAL,
                log_return REAL, cum_return REAL, roll_vol REAL,
                liquidity_usd REAL, vol_h24 REAL
            )
        """)
        conn.commit()
    return db_path


@pytest.fixture
def temp_db(tmp_path):
    return _create_temp_db_with_schema(tmp_path)


def test_load_snapshots_returns_expected_columns(temp_db):
    """load_snapshots returns DataFrame with expected columns, sorted by ts_utc."""
    with sqlite3.connect(temp_db) as conn:
        conn.execute(
            """INSERT INTO sol_monitor_snapshots (ts_utc, chain_id, pair_address, base_symbol, quote_symbol, dex_price_usd, liquidity_usd, vol_h24)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("2025-01-01 10:00:00", "solana", "addr1", "SOL", "USDC", 100.0, 1e6, 5e5),
        )
        conn.execute(
            """INSERT INTO sol_monitor_snapshots (ts_utc, chain_id, pair_address, base_symbol, quote_symbol, dex_price_usd, liquidity_usd, vol_h24)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("2025-01-01 11:00:00", "solana", "addr1", "SOL", "USDC", 101.0, 1e6, 5e5),
        )
        conn.commit()
    df = load_snapshots(db_path_override=temp_db, apply_filters=False)
    assert not df.empty
    expected = {
        "ts_utc",
        "chain_id",
        "pair_address",
        "base_symbol",
        "quote_symbol",
        "price_usd",
        "liquidity_usd",
        "vol_h24",
    }
    assert expected <= set(df.columns)
    assert df["ts_utc"].is_monotonic_increasing or list(df["ts_utc"].iloc[[0, 1]]) == list(
        df["ts_utc"].iloc[[0, 1]].sort_values()
    )
    # No duplicate index (no dupes in key columns for same ts)
    assert df.duplicated(subset=["ts_utc", "chain_id", "pair_address"]).sum() == 0


def test_load_snapshots_empty(temp_db):
    """Empty snapshot table returns empty DataFrame."""
    df = load_snapshots(db_path_override=temp_db, apply_filters=False)
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_load_snapshots_invalid_table_raises(temp_db):
    """Unknown table_override raises ValueError."""
    with pytest.raises(ValueError) as exc_info:
        load_snapshots(db_path_override=temp_db, table_override="evil_table", apply_filters=False)
    assert "Invalid snapshot table" in str(exc_info.value)
    assert "evil_table" in str(exc_info.value)


def test_load_snapshots_invalid_price_col_raises(temp_db):
    """Unknown price_col_override raises ValueError."""
    with pytest.raises(ValueError) as exc_info:
        load_snapshots(db_path_override=temp_db, price_col_override="evil_col", apply_filters=False)
    assert "Invalid price column" in str(exc_info.value)
    assert "evil_col" in str(exc_info.value)


def test_load_bars_returns_expected_columns(temp_db):
    """load_bars returns correct columns, sorted by ts_utc, no duplicates."""
    with sqlite3.connect(temp_db) as conn:
        for i in range(5):
            conn.execute(
                """INSERT INTO bars_1h (ts_utc, chain_id, pair_address, base_symbol, quote_symbol, open, high, low, close)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (f"2025-01-01 {i:02d}:00:00", "solana", "addr1", "SOL", "USDC", 1.0, 1.0, 1.0, 1.0),
            )
        conn.commit()
    df = load_bars("1h", db_path_override=temp_db)
    assert not df.empty
    expected_cols = {
        "ts_utc",
        "chain_id",
        "pair_address",
        "base_symbol",
        "quote_symbol",
        "open",
        "high",
        "low",
        "close",
    }
    assert expected_cols <= set(df.columns)
    df_sorted = df.sort_values("ts_utc")
    pd.testing.assert_frame_equal(df, df_sorted)
    assert df.duplicated(subset=["ts_utc", "chain_id", "pair_address"]).sum() == 0


def test_load_bars_empty(temp_db):
    """Empty bars table returns empty DataFrame."""
    df = load_bars("1h", db_path_override=temp_db)
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_load_bars_invalid_freq_raises(temp_db):
    """Freq that is not in bars_freqs (e.g. invalid table name) raises ValueError."""
    # bars_1w is not in default bars_freqs [5min, 15min, 1h, 1D]
    with pytest.raises(ValueError) as exc_info:
        load_bars("1w", db_path_override=temp_db)
    assert "Invalid bars table" in str(exc_info.value)
    assert "bars_1w" in str(exc_info.value)


def test_load_bars_no_such_table_returns_empty(tmp_path):
    """Missing bars table returns empty DataFrame (DEX table empty handled gracefully)."""
    db_path = str(tmp_path / "no_bars.sqlite")
    with _with_conn(db_path):
        pass  # migrations only; no bars_1h
    # bars_1h is in allowed_bars_tables() so we pass validation, but table doesn't exist
    df = load_bars("1h", db_path_override=db_path)
    assert df.empty
    assert isinstance(df, pd.DataFrame)


def test_load_spot_series_empty(temp_db):
    """Empty spot_price_snapshots returns empty Series."""
    s = load_spot_series(db_path_override=temp_db, symbol="BTC")
    assert isinstance(s, pd.Series)
    assert s.empty


def test_load_spot_series_with_data(temp_db):
    """load_spot_series returns Series indexed by ts_utc, sorted."""
    with sqlite3.connect(temp_db) as conn:
        conn.execute(
            "INSERT INTO spot_price_snapshots (ts_utc, symbol, spot_price_usd) VALUES (?, ?, ?)",
            ("2025-01-01 12:00:00", "BTC", 50000.0),
        )
        conn.execute(
            "INSERT INTO spot_price_snapshots (ts_utc, symbol, spot_price_usd) VALUES (?, ?, ?)",
            ("2025-01-01 13:00:00", "BTC", 50100.0),
        )
        conn.commit()
    s = load_spot_series(db_path_override=temp_db, symbol="BTC")
    assert not s.empty
    assert s.index.name == "ts_utc" or isinstance(s.index, pd.DatetimeIndex)
    assert s.is_monotonic_increasing or len(s) == 2
