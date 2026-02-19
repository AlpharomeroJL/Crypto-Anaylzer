"""
Materialize factor model runs to SQLite: factor_model_runs, factor_betas, residual_returns.
Uses causal rolling OLS (as_of_lag_bars=1). factor_run_id is stable hash of dataset_id + config.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from .factors import causal_rolling_ols
from .timeutils import now_utc_iso


@dataclass
class FactorMaterializeConfig:
    """Config for one factor run; used for factor_run_id hash."""

    dataset_id: str
    freq: str
    window_bars: int
    min_obs: int
    factors: List[str]
    estimator: str = "rolling_ols"
    params: Optional[dict] = None

    def to_canonical_dict(self) -> dict:
        d = {
            "dataset_id": self.dataset_id,
            "freq": self.freq,
            "window_bars": self.window_bars,
            "min_obs": self.min_obs,
            "factors": sorted(self.factors),
            "estimator": self.estimator,
        }
        if self.params is not None:
            d["params"] = dict(sorted((self.params or {}).items()))
        return d


def compute_factor_run_id(config: FactorMaterializeConfig) -> str:
    """Stable factor_run_id from dataset_id + config (sorted keys, canonical JSON)."""
    canonical = json.dumps(config.to_canonical_dict(), sort_keys=True, separators=(",", ":"))
    h = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"fctr_{h[:16]}"


def materialize_factor_run(
    conn: sqlite3.Connection,
    returns_df: pd.DataFrame,
    config: FactorMaterializeConfig,
    *,
    created_at_utc: Optional[str] = None,
) -> str:
    """
    Compute causal rolling OLS (as_of_lag_bars=1), write factor_model_runs row and
    bulk insert factor_betas and residual_returns. Idempotent: same factor_run_id
    deletes existing rows and re-inserts.

    returns_df: wide DataFrame index=ts_utc, columns=asset_ids + factor columns (e.g. BTC_spot, ETH_spot).
    Returns factor_run_id.
    """
    factor_run_id = compute_factor_run_id(config)
    created_at_utc = created_at_utc or now_utc_iso()
    factors_json = json.dumps(config.factors)
    params_json = json.dumps(config.params) if config.params else None

    result = causal_rolling_ols(
        returns_df,
        factor_cols=config.factors,
        window_bars=config.window_bars,
        min_obs=config.min_obs,
        as_of_lag_bars=1,
        add_const=True,
    )
    betas_dict, r2_df, residual_df, alpha_df = result
    if not betas_dict or not residual_df.columns.tolist():
        conn.execute(
            """INSERT OR REPLACE INTO factor_model_runs
               (factor_run_id, created_at_utc, dataset_id, freq, window_bars, min_obs, factors_json, estimator, params_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                factor_run_id,
                created_at_utc,
                config.dataset_id,
                config.freq,
                config.window_bars,
                config.min_obs,
                factors_json,
                config.estimator,
                params_json,
            ),
        )
        conn.commit()
        return factor_run_id

    conn.execute("DELETE FROM factor_betas WHERE factor_run_id = ?", (factor_run_id,))
    conn.execute("DELETE FROM residual_returns WHERE factor_run_id = ?", (factor_run_id,))
    conn.execute(
        """INSERT OR REPLACE INTO factor_model_runs
           (factor_run_id, created_at_utc, dataset_id, freq, window_bars, min_obs, factors_json, estimator, params_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            factor_run_id,
            created_at_utc,
            config.dataset_id,
            config.freq,
            config.window_bars,
            config.min_obs,
            factors_json,
            config.estimator,
            params_json,
        ),
    )

    common_idx = residual_df.index
    asset_cols = sorted(residual_df.columns.tolist())
    factor_names = sorted(betas_dict.keys())

    beta_rows: List[tuple] = []
    for ts in sorted(common_idx):
        ts_str = str(ts)
        for asset in asset_cols:
            r2_val = r2_df.loc[ts, asset] if ts in r2_df.index and asset in r2_df.columns else None
            if pd.isna(r2_val):
                r2_val = None
            alpha_val = alpha_df.loc[ts, asset] if ts in alpha_df.index and asset in alpha_df.columns else None
            if pd.isna(alpha_val):
                alpha_val = None
            else:
                alpha_val = float(alpha_val)
            for fname in factor_names:
                b_df = betas_dict[fname]
                if ts not in b_df.index or asset not in b_df.columns:
                    continue
                beta_val = b_df.loc[ts, asset]
                if pd.isna(beta_val):
                    continue
                beta_rows.append(
                    (
                        factor_run_id,
                        ts_str,
                        asset,
                        fname,
                        float(beta_val),
                        alpha_val,
                        float(r2_val) if r2_val is not None else None,
                    )
                )

    if beta_rows:
        beta_rows.sort(key=lambda r: (r[1], r[2], r[3]))  # ts_utc, asset_id, factor_name
        conn.executemany(
            """INSERT INTO factor_betas (factor_run_id, ts_utc, asset_id, factor_name, beta, alpha, r2)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            beta_rows,
        )

    resid_rows: List[tuple] = []
    for ts in sorted(common_idx):
        ts_str = str(ts)
        for asset in asset_cols:
            v = residual_df.loc[ts, asset]
            if pd.isna(v):
                continue
            resid_rows.append((factor_run_id, ts_str, asset, float(v)))
    if resid_rows:
        resid_rows.sort(key=lambda r: (r[1], r[2]))  # ts_utc, asset_id
        conn.executemany(
            """INSERT INTO residual_returns (factor_run_id, ts_utc, asset_id, resid_log_return)
               VALUES (?, ?, ?, ?)""",
            resid_rows,
        )

    conn.commit()
    return factor_run_id
