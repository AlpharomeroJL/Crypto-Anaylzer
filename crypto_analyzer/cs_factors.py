"""
Cross-sectional factor model: size, liquidity, momentum factors scored per timestamp.
Research-only; no execution.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def safe_log(x: pd.Series) -> pd.Series:
    """Elementwise log; NaN for non-positive values."""
    return np.log(x.where(x > 0))


def winsorize_series(s: pd.Series, p: float = 0.01) -> pd.Series:
    """Clip values at the *p* and *1-p* quantiles."""
    valid = s.dropna()
    if len(valid) < 2:
        return s.copy()
    lo = valid.quantile(p)
    hi = valid.quantile(1 - p)
    return s.clip(lower=lo, upper=hi)


def cs_zscore(group: pd.Series) -> pd.Series:
    """Cross-sectional z-score (mean 0, std 1). Returns NaN if <3 values or std==0."""
    valid = group.dropna()
    if len(valid) < 3:
        return pd.Series(np.nan, index=group.index)
    mu = valid.mean()
    sigma = valid.std(ddof=1)
    if sigma == 0:
        return pd.Series(np.nan, index=group.index)
    return (group - mu) / sigma


def build_cs_factor_frame(
    bars_df: pd.DataFrame,
    freq: str,
    lookback: int = 24,
    winsorize_p: float = 0.01,
    zscore: bool = True,
) -> pd.DataFrame:
    """Build long-form factor DataFrame with columns [ts_utc, pair_key, factor_name, value].

    Requires bars_df to contain: ts_utc, chain_id, pair_address, close,
    log_return, liquidity_usd, vol_h24.
    Timestamps with <3 assets are dropped.
    """
    df = bars_df.copy()
    df["pair_key"] = df["chain_id"].astype(str) + ":" + df["pair_address"].astype(str)
    df = df.sort_values(["pair_key", "ts_utc"])

    df["cum_mom"] = (
        df.groupby("pair_key")["log_return"]
        .rolling(lookback, min_periods=1)
        .sum()
        .reset_index(level=0, drop=True)
    )

    records: list[dict] = []

    for ts, grp in df.groupby("ts_utc"):
        if len(grp) < 3:
            continue

        size_raw = safe_log(grp["liquidity_usd"])
        liq_raw = safe_log(grp["vol_h24"])
        mom_raw = grp["cum_mom"]

        size_w = winsorize_series(size_raw, winsorize_p)
        liq_w = winsorize_series(liq_raw, winsorize_p)
        mom_w = winsorize_series(mom_raw, winsorize_p)

        if zscore:
            size_v = cs_zscore(size_w)
            liq_v = cs_zscore(liq_w)
            mom_v = cs_zscore(mom_w)
        else:
            size_v = size_w
            liq_v = liq_w
            mom_v = mom_w

        for idx_row in grp.index:
            pk = grp.at[idx_row, "pair_key"]
            records.append({"ts_utc": ts, "pair_key": pk, "factor_name": "size_factor", "value": size_v.get(idx_row, np.nan)})
            records.append({"ts_utc": ts, "pair_key": pk, "factor_name": "liquidity_factor", "value": liq_v.get(idx_row, np.nan)})
            records.append({"ts_utc": ts, "pair_key": pk, "factor_name": "momentum_factor", "value": mom_v.get(idx_row, np.nan)})

    if not records:
        return pd.DataFrame(columns=["ts_utc", "pair_key", "factor_name", "value"])

    return pd.DataFrame(records)
