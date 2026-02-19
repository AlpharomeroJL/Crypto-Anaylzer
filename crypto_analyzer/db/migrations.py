"""
Idempotent database migrations.

All schema changes use CREATE TABLE IF NOT EXISTS and guarded ALTER TABLE
so they can be re-run safely at any time.
"""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)


def _safe_add_column(conn: sqlite3.Connection, table: str, column: str, col_type: str) -> None:
    """Add a column if it doesn't already exist."""
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type};")
        conn.commit()
        logger.debug("Added column %s.%s", table, column)
    except sqlite3.OperationalError:
        pass


def run_migrations(conn: sqlite3.Connection) -> None:
    """
    Apply all schema migrations idempotently.

    Safe to call on every startup — only creates/alters what's missing.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sol_monitor_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc TEXT NOT NULL,
            chain_id TEXT NOT NULL,
            pair_address TEXT NOT NULL,
            dex_id TEXT,
            base_symbol TEXT,
            quote_symbol TEXT,
            dex_price_usd REAL,
            dex_price_native REAL,
            liquidity_usd REAL,
            vol_h24 REAL,
            txns_h24_buys INTEGER,
            txns_h24_sells INTEGER,
            spot_source TEXT,
            spot_price_usd REAL,
            raw_pair_json TEXT
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sol_monitor_ts ON sol_monitor_snapshots(ts_utc);")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS spot_price_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc TEXT NOT NULL,
            symbol TEXT NOT NULL,
            spot_price_usd REAL NOT NULL,
            spot_source TEXT
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_spot_ts_symbol ON spot_price_snapshots(ts_utc, symbol);")

    # Provenance fields on spot_price_snapshots
    _safe_add_column(conn, "spot_price_snapshots", "provider_name", "TEXT")
    _safe_add_column(conn, "spot_price_snapshots", "fetched_at_utc", "TEXT")
    _safe_add_column(conn, "spot_price_snapshots", "fetch_status", "TEXT")
    _safe_add_column(conn, "spot_price_snapshots", "error_message", "TEXT")

    # Provenance fields on sol_monitor_snapshots
    _safe_add_column(conn, "sol_monitor_snapshots", "provider_name", "TEXT")
    _safe_add_column(conn, "sol_monitor_snapshots", "fetched_at_utc", "TEXT")
    _safe_add_column(conn, "sol_monitor_snapshots", "fetch_status", "TEXT")
    _safe_add_column(conn, "sol_monitor_snapshots", "error_message", "TEXT")

    # Universe tables
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS universe_allowlist (
            ts_utc TEXT NOT NULL,
            chain_id TEXT NOT NULL,
            pair_address TEXT NOT NULL,
            label TEXT,
            liquidity_usd REAL,
            vol_h24 REAL,
            source TEXT,
            query_summary TEXT,
            PRIMARY KEY (ts_utc, chain_id, pair_address)
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_universe_allowlist_ts ON universe_allowlist(ts_utc);")
    _safe_add_column(conn, "universe_allowlist", "reason_added", "TEXT")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS universe_persistence (
            chain_id TEXT NOT NULL,
            pair_address TEXT NOT NULL,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            updated_ts TEXT NOT NULL,
            PRIMARY KEY (chain_id, pair_address)
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS universe_churn_log (
            ts_utc TEXT NOT NULL,
            chain_id TEXT NOT NULL,
            pair_address TEXT NOT NULL,
            action TEXT NOT NULL,
            reason TEXT,
            liquidity_usd REAL,
            vol_h24 REAL,
            PRIMARY KEY (ts_utc, chain_id, pair_address)
        );
        """
    )

    # Provider health tracking
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_health (
            provider_name TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'OK',
            last_ok_at TEXT,
            fail_count INTEGER NOT NULL DEFAULT 0,
            disabled_until TEXT,
            last_error TEXT,
            updated_at TEXT NOT NULL
        );
        """
    )

    conn.commit()
    logger.debug("Database migrations complete")
