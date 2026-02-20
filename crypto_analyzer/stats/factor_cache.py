"""
Factor materialization cache: validate DB hit before skipping compute.
Phase 3 PR3. Rowcount + metadata invariants; no silent reuse.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

import pandas as pd


def factor_run_exists(conn: sqlite3.Connection, factor_run_id: str) -> Optional[Dict[str, Any]]:
    """Return factor_model_runs row as dict if exists, else None."""
    cur = conn.execute(
        "SELECT factor_run_id, dataset_id, freq, window_bars, min_obs, factors_json, estimator, params_json "
        "FROM factor_model_runs WHERE factor_run_id = ?",
        (factor_run_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "factor_run_id": row[0],
        "dataset_id": row[1],
        "freq": row[2],
        "window_bars": row[3],
        "min_obs": row[4],
        "factors_json": row[5],
        "estimator": row[6],
        "params_json": row[7],
    }


def factor_run_matches_invocation(
    row: Dict[str, Any],
    dataset_id: str,
    freq: str,
    window_bars: int,
    min_obs: int,
    params_json: Optional[str],
) -> bool:
    """True if stored metadata matches this invocation (1-row read already done)."""
    if row is None:
        return False
    if row.get("dataset_id") != dataset_id:
        return False
    if row.get("freq") != freq:
        return False
    if row.get("window_bars") != window_bars:
        return False
    if row.get("min_obs") != min_obs:
        return False
    stored_params = row.get("params_json")
    if stored_params != params_json:
        if stored_params is None and params_json is None:
            pass
        elif stored_params is None or params_json is None:
            return False
        else:
            try:
                if json.loads(stored_params) != json.loads(params_json):
                    return False
            except (json.JSONDecodeError, TypeError):
                return False
    return True


def factor_run_rowcounts_match(
    conn: sqlite3.Connection,
    factor_run_id: str,
    expected_betas: int,
    expected_resids: int,
) -> bool:
    """True if stored factor_betas and residual_returns counts match expected."""
    cur_b = conn.execute("SELECT COUNT(*) FROM factor_betas WHERE factor_run_id = ?", (factor_run_id,))
    cur_r = conn.execute("SELECT COUNT(*) FROM residual_returns WHERE factor_run_id = ?", (factor_run_id,))
    got_b = cur_b.fetchone()[0]
    got_r = cur_r.fetchone()[0]
    return got_b == expected_betas and got_r == expected_resids


def expected_factor_rowcounts_from_shape(
    returns_df: pd.DataFrame,
    window_bars: int,
    factors: List[str],
    *,
    add_const: bool = True,
) -> tuple[int, int]:
    """
    Estimate expected factor_betas and residual_returns row counts from input shape.
    Used to validate cache hit without running OLS. Conservative: valid-ts count
    mirrors window (n_ts - window_bars + 1); min_obs/as_of_lag_bars may reduce
    actual inserted rows, so this can underestimate and cause cache miss (safe).
    Cache hit requires exact match to stored counts.
    """
    n_ts = len(returns_df.index)
    n_valid_ts = max(0, n_ts - window_bars + 1)
    # Assets = columns of returns that get residuals (all non-factor columns or all if factors are subset)
    asset_cols = [c for c in returns_df.columns if c not in factors]
    n_assets = len(asset_cols) if asset_cols else len(returns_df.columns)
    n_factors = len(factors) + (1 if add_const else 0)
    expected_resids = n_valid_ts * n_assets
    expected_betas = n_valid_ts * n_assets * n_factors
    return expected_betas, expected_resids
