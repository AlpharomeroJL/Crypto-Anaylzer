"""
Signals journal: log research signals (no trading). SQLite table signals_log.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

SIGNALS_TABLE = "signals_log"


def ensure_signals_table(conn: sqlite3.Connection) -> None:
    """Create signals_log if not exists. ts_utc TEXT, signal TEXT, label TEXT, value REAL, threshold REAL, meta_json TEXT."""
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SIGNALS_TABLE} (
            ts_utc TEXT,
            signal TEXT,
            label TEXT,
            value REAL,
            threshold REAL,
            meta_json TEXT
        )
    """)
    conn.commit()


def log_signals(db_path: str, rows: List[Dict[str, Any]]) -> None:
    """Append rows to signals_log. Each row: ts_utc, signal, label, value, threshold, meta_json (optional)."""
    if not rows:
        return
    with sqlite3.connect(db_path) as con:
        ensure_signals_table(con)
        for r in rows:
            ts = r.get("ts_utc")
            if ts is None:
                ts = datetime.now(timezone.utc).isoformat()
            if hasattr(ts, "isoformat"):
                ts = ts.isoformat()
            meta = r.get("meta_json")
            if isinstance(meta, dict):
                meta = json.dumps(meta)
            con.execute(
                f"INSERT INTO {SIGNALS_TABLE} (ts_utc, signal, label, value, threshold, meta_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(ts),
                    str(r.get("signal", "")),
                    str(r.get("label", "")),
                    float(r["value"]) if r.get("value") is not None and not np.isnan(r["value"]) else None,
                    float(r["threshold"]) if r.get("threshold") is not None and not np.isnan(r["threshold"]) else None,
                    meta,
                ),
            )
        con.commit()


def detect_signals(
    beta_btc_24: Optional[float],
    beta_btc_72: Optional[float],
    dispersion_z: Optional[float],
    residual_return_24h: Optional[float],
    label: str,
    *,
    beta_compress_threshold: float = 0.15,
    dispersion_z_high: float = 1.0,
    dispersion_z_low: float = -1.0,
    residual_momentum_threshold: float = 0.01,
) -> List[Dict[str, Any]]:
    """
    Given latest metrics and thresholds, return list of signal rows to log.
    - beta_compression_trigger: beta_btc_24 < beta_btc_72 - threshold
    - dispersion_extreme: dispersion_z > +Z or < -Z
    - residual_momentum: residual_return_24h > R
    """
    rows = []
    ts = datetime.now(timezone.utc)

    if beta_btc_24 is not None and beta_btc_72 is not None and not (np.isnan(beta_btc_24) or np.isnan(beta_btc_72)):
        if beta_btc_24 < beta_btc_72 - beta_compress_threshold:
            rows.append({
                "ts_utc": ts,
                "signal": "beta_compression_trigger",
                "label": label,
                "value": float(beta_btc_24),
                "threshold": float(beta_btc_72 - beta_compress_threshold),
                "meta_json": {"beta_btc_24": beta_btc_24, "beta_btc_72": beta_btc_72},
            })

    if dispersion_z is not None and not np.isnan(dispersion_z):
        if dispersion_z > dispersion_z_high:
            rows.append({
                "ts_utc": ts,
                "signal": "dispersion_extreme",
                "label": label,
                "value": float(dispersion_z),
                "threshold": dispersion_z_high,
                "meta_json": {"side": "high"},
            })
        elif dispersion_z < dispersion_z_low:
            rows.append({
                "ts_utc": ts,
                "signal": "dispersion_extreme",
                "label": label,
                "value": float(dispersion_z),
                "threshold": dispersion_z_low,
                "meta_json": {"side": "low"},
            })

    if residual_return_24h is not None and not np.isnan(residual_return_24h):
        if residual_return_24h > residual_momentum_threshold:
            rows.append({
                "ts_utc": ts,
                "signal": "residual_momentum",
                "label": label,
                "value": float(residual_return_24h),
                "threshold": residual_momentum_threshold,
                "meta_json": {},
            })

    return rows


def load_signals(db_path: str, signal_type: Optional[str] = None, last_n: int = 100) -> pd.DataFrame:
    """Load last N signals; optionally filter by signal type."""
    with sqlite3.connect(db_path) as con:
        ensure_signals_table(con)
        if signal_type:
            df = pd.read_sql_query(
                f"SELECT * FROM {SIGNALS_TABLE} WHERE signal = ? ORDER BY ts_utc DESC LIMIT ?",
                con,
                params=(signal_type, last_n),
            )
        else:
            df = pd.read_sql_query(
                f"SELECT * FROM {SIGNALS_TABLE} ORDER BY ts_utc DESC LIMIT ?",
                con,
                params=(last_n,),
            )
    if df.empty:
        return df
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    return df
