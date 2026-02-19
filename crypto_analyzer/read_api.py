"""
Read-only API for dashboard and CLI: provider health, spot provenance, universe allowlist.

CLI/Streamlit should use this (and ingest.get_provider_health) instead of importing
crypto_analyzer.db or opening SQLite directly.
"""

from __future__ import annotations

import sqlite3
from typing import Optional, Tuple

import pandas as pd

from .db.migrations import run_migrations


def _with_conn(db_path: str):
    """Context manager for read-only DB access with migrations applied."""
    conn = sqlite3.connect(db_path)
    try:
        run_migrations(conn)
        yield conn
    finally:
        conn.close()


def load_spot_snapshots_recent(db_path: str, limit: int = 15) -> pd.DataFrame:
    """Latest spot_price_snapshots rows (ts_utc, symbol, spot_price_usd, spot_source, provider_name, fetch_status)."""
    with _with_conn(db_path) as con:
        return pd.read_sql_query(
            """SELECT ts_utc, symbol, spot_price_usd, spot_source,
                      provider_name, fetch_status
               FROM spot_price_snapshots
               ORDER BY id DESC LIMIT ?""",
            con,
            params=(limit,),
        )


def load_latest_universe_allowlist(db_path: str, limit: int = 20) -> pd.DataFrame:
    """Top N rows from universe_allowlist for latest ts_utc (label, chain_id, pair_address, liquidity_usd, vol_h24, source)."""
    try:
        with _with_conn(db_path) as con:
            return pd.read_sql_query(
                """SELECT label, chain_id, pair_address, liquidity_usd, vol_h24, source
                   FROM universe_allowlist
                   WHERE ts_utc = (SELECT MAX(ts_utc) FROM universe_allowlist)
                   ORDER BY liquidity_usd DESC LIMIT ?""",
                con,
                params=(limit,),
            )
    except (sqlite3.OperationalError, Exception):
        return pd.DataFrame()


def load_universe_allowlist_stats(db_path: str) -> Tuple[Optional[str], int, int]:
    """Returns (latest_ts_utc, universe_size_at_latest, n_refreshes)."""
    try:
        with _with_conn(db_path) as con:
            cur = con.execute("SELECT MAX(ts_utc), COUNT(DISTINCT ts_utc) FROM universe_allowlist")
            row = cur.fetchone()
            latest_ts = row[0] if row and row[0] else None
            n_refreshes = row[1] if row and row[1] else 0
            if latest_ts:
                cur = con.execute(
                    "SELECT COUNT(*) FROM universe_allowlist WHERE ts_utc = ?",
                    (latest_ts,),
                )
                universe_size = cur.fetchone()[0]
            else:
                universe_size = 0
            return (latest_ts, universe_size, n_refreshes)
    except Exception:
        return (None, 0, 0)


def load_universe_churn_verification(db_path: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Allowlist last 5 refreshes and churn at last refresh. Returns (allowlist_df, churn_df)."""
    try:
        with _with_conn(db_path) as con:
            allowlist_ver = pd.read_sql_query(
                """SELECT ts_utc, COUNT(*) AS n, MIN(source) AS sources_hint
                   FROM universe_allowlist
                   GROUP BY ts_utc ORDER BY ts_utc DESC LIMIT 5""",
                con,
            )
            churn_ver = pd.read_sql_query(
                """SELECT action, reason, COUNT(*) AS n
                   FROM universe_churn_log
                   WHERE ts_utc = (SELECT MAX(ts_utc) FROM universe_churn_log)
                   GROUP BY action, reason ORDER BY n DESC""",
                con,
            )
            return (allowlist_ver, churn_ver)
    except Exception:
        return (pd.DataFrame(), pd.DataFrame())
