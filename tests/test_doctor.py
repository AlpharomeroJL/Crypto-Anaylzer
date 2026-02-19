"""
Tests for crypto_analyzer.doctor: exit codes, DB checks, minimal schema.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

# Ensure package on path when running tests from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crypto_analyzer import doctor


def _make_minimal_db(path: str) -> None:
    """Create a minimal SQLite DB with required tables and columns for doctor + pipeline smoke."""
    with sqlite3.connect(path) as con:
        con.execute("""
            CREATE TABLE sol_monitor_snapshots (
                ts_utc TEXT, chain_id TEXT, pair_address TEXT,
                base_symbol TEXT, quote_symbol TEXT, dex_price_usd REAL,
                liquidity_usd REAL, vol_h24 REAL
            )
        """)
        con.execute("""
            CREATE TABLE spot_price_snapshots (
                ts_utc TEXT, symbol TEXT, spot_price_usd REAL
            )
        """)
        con.execute("""
            CREATE TABLE bars_1h (
                ts_utc TEXT, chain_id TEXT, pair_address TEXT,
                base_symbol TEXT, quote_symbol TEXT,
                open REAL, high REAL, low REAL, close REAL,
                log_return REAL, cum_return REAL, roll_vol REAL,
                liquidity_usd REAL, vol_h24 REAL
            )
        """)
        # One row each so tables exist; bars_1h needs enough for min_bars (e.g. 48) for one pair
        con.execute(
            "INSERT INTO sol_monitor_snapshots (ts_utc, chain_id, pair_address, dex_price_usd) VALUES (?, ?, ?, ?)",
            ("2025-01-01 00:00:00", "solana", "addr1", 1.0),
        )
        con.execute(
            "INSERT INTO spot_price_snapshots (ts_utc, symbol, spot_price_usd) VALUES (?, ?, ?)",
            ("2025-01-01 00:00:00", "BTC", 50000.0),
        )
        for i in range(50):
            con.execute(
                """INSERT INTO bars_1h (ts_utc, chain_id, pair_address, base_symbol, quote_symbol, open, high, low, close)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (f"2025-01-01 {i:02d}:00:00", "solana", "addr1", "SOL", "USDC", 1.0, 1.0, 1.0, 1.0),
            )
        con.commit()


def test_doctor_check_db_fails_when_db_missing(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        missing = os.path.join(tmp, "nonexistent.sqlite")
        assert not os.path.isfile(missing)
        monkeypatch.setattr(doctor, "_get_db_path", lambda: missing)
        assert doctor.check_db() is False


def test_doctor_check_db_passes_with_minimal_schema(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        _make_minimal_db(path)
        monkeypatch.setattr(doctor, "_get_db_path", lambda: path)
        assert doctor.check_db() is True
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


def test_doctor_main_exit_3_when_db_missing(monkeypatch):
    monkeypatch.setattr(doctor, "check_env", lambda: True)
    monkeypatch.setattr(doctor, "check_dependencies", lambda: True)
    with tempfile.TemporaryDirectory() as tmp:
        missing = os.path.join(tmp, "nonexistent.sqlite")
        monkeypatch.setattr(doctor, "_get_db_path", lambda: missing)
        assert doctor.main() == 3


def test_doctor_main_exit_0_with_minimal_db(monkeypatch):
    monkeypatch.setattr(doctor, "check_env", lambda: True)
    monkeypatch.setattr(doctor, "check_dependencies", lambda: True)
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        _make_minimal_db(path)
        monkeypatch.setattr(doctor, "_get_db_path", lambda: path)
        assert doctor.main() == 0
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass
