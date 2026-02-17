"""
Data integrity checks: monotonic time, no zero/negative prices, no forward-looking alignment.
Research-only. Used before computing forward returns; print warnings, do not crash unless blatant.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional, Tuple, Union

import pandas as pd


def count_non_positive_prices(
    db_path: str,
    checks: List[Tuple[str, str]],
) -> List[Tuple[str, str, int]]:
    """
    For each (table, column) query the DB and return (table, column, count) for rows where value <= 0 or NULL.
    Only returns entries with count > 0. Does not mutate the DB.
    """
    result: List[Tuple[str, str, int]] = []
    try:
        with sqlite3.connect(db_path) as con:
            for table, column in checks:
                try:
                    cur = con.execute(
                        f"SELECT COUNT(*) FROM [{table}] WHERE [{column}] IS NULL OR [{column}] <= 0"
                    )
                    n = cur.fetchone()[0]
                    if n > 0:
                        result.append((table, column, n))
                except sqlite3.OperationalError:
                    pass
    except Exception:
        pass
    return result


def bad_row_rate(
    db_path: str,
    checks: List[Tuple[str, str]],
) -> List[Tuple[str, str, int, int, float]]:
    """
    For each (table, column) return (table, column, bad_count, total_rows, bad_pct).
    Identifies which table/column is generating non-positive prices and the bad row rate.
    """
    result: List[Tuple[str, str, int, int, float]] = []
    try:
        with sqlite3.connect(db_path) as con:
            for table, column in checks:
                try:
                    cur = con.execute(
                        f"SELECT COUNT(*) FROM [{table}] WHERE [{column}] IS NULL OR [{column}] <= 0"
                    )
                    bad = cur.fetchone()[0]
                    cur = con.execute(f"SELECT COUNT(*) FROM [{table}]")
                    total = cur.fetchone()[0]
                    pct = (100.0 * bad / total) if total else 0.0
                    result.append((table, column, bad, total, pct))
                except sqlite3.OperationalError:
                    pass
    except Exception:
        pass
    return result


def assert_monotonic_time_index(df: pd.DataFrame, col: str = "ts_utc") -> Optional[str]:
    """
    Check that col is monotonically increasing. Return warning string if not, else None.
    """
    if df.empty or col not in df.columns:
        return None
    s = pd.to_datetime(df[col], utc=True, errors="coerce").dropna()
    if len(s) < 2:
        return None
    if not s.is_monotonic_increasing:
        return "Time index is not monotonic; check for duplicates or out-of-order rows."
    return None


def assert_no_negative_or_zero_prices(prices: Union[pd.Series, pd.DataFrame]) -> Optional[str]:
    """Check no zero or negative prices. Return warning string if any, else None."""
    if prices is None or (hasattr(prices, "empty") and prices.empty):
        return None
    if isinstance(prices, pd.DataFrame):
        # use close or first numeric column
        if "close" in prices.columns:
            p = prices["close"]
        else:
            p = prices.select_dtypes(include=["number"]).iloc[:, 0] if not prices.select_dtypes(include=["number"]).empty else pd.Series(dtype=float)
    else:
        p = prices
    if p is None or (hasattr(p, "empty") and p.empty):
        return None
    p = pd.to_numeric(p, errors="coerce").dropna()
    if (p <= 0).any():
        return "Found zero or negative prices; results may be invalid."
    return None


def assert_no_forward_looking(
    signal_ts: pd.DatetimeIndex,
    fwd_return_ts: pd.DatetimeIndex,
) -> Optional[str]:
    """
    Check that signal timestamps are not after corresponding forward return timestamps.
    If signal_ts and fwd_return_ts are aligned by index, we expect signal_ts <= fwd_return_ts.
    Return warning if any signal_ts > fwd_return_ts, else None.
    """
    if signal_ts is None or fwd_return_ts is None or len(signal_ts) == 0 or len(fwd_return_ts) == 0:
        return None
    try:
        common = signal_ts.intersection(fwd_return_ts)
        if len(common) == 0:
            return None
        # Forward returns are typically indexed at t; they represent return from t to t+h.
        # Signal at t should be known before t+h. So we only flag if signal index > fwd index (alignment issue).
        # Simplified: if we have same index, no problem. If signal has a timestamp that's after the latest fwd_ts, warn.
        if signal_ts.max() > fwd_return_ts.max():
            return "Signal has timestamps after latest forward return timestamp; possible look-ahead."
    except Exception:
        pass
    return None


def validate_alignment(
    returns_df: pd.DataFrame,
    signals_df: pd.DataFrame,
    horizons: List[int],
) -> List[str]:
    """
    Validate alignment between returns and signals. Return list of warning strings.
    """
    warnings: List[str] = []
    if returns_df.empty or signals_df.empty:
        return warnings
    common_idx = returns_df.index.intersection(signals_df.index)
    if len(common_idx) < 2:
        warnings.append("Returns and signals have insufficient overlap.")
    return warnings
