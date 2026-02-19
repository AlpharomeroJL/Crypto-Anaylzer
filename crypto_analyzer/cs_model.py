"""
Cross-sectional signal combiner: aggregate factor scores into composite signal.
Research-only; no execution.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

_DEFAULT_WEIGHTS: Dict[str, float] = {
    "size_factor": 0.2,
    "liquidity_factor": 0.2,
    "momentum_factor": 0.6,
}


def combine_factors(
    cs_factor_df: pd.DataFrame,
    weights: Optional[Dict[str, float]] = None,
    method: str = "linear",
) -> pd.DataFrame:
    """Combine per-timestamp factor scores into a single composite signal.

    *method*: ``"linear"`` (weighted sum) or ``"rank_sum"`` (sum of within-timestamp ranks).
    Timestamps with <3 assets are dropped.
    """
    if weights is None:
        weights = _DEFAULT_WEIGHTS.copy()

    if method == "linear":
        return _combine_linear(cs_factor_df, weights)
    if method == "rank_sum":
        return _combine_rank_sum(cs_factor_df)
    raise ValueError(f"Unknown method: {method}")


def _combine_linear(df: pd.DataFrame, weights: Dict[str, float]) -> pd.DataFrame:
    """Weighted sum of factor values per (ts_utc, pair_key)."""
    records: list[dict] = []
    for (ts, pk), grp in df.groupby(["ts_utc", "pair_key"]):
        total = 0.0
        for _, row in grp.iterrows():
            w = weights.get(row["factor_name"], 0.0)
            v = row["value"]
            if np.isnan(v):
                total = np.nan
                break
            total += w * v
        records.append({"ts_utc": ts, "pair_key": pk, "signal": total})

    result = pd.DataFrame(records)
    return _filter_min_assets(result)


def _combine_rank_sum(df: pd.DataFrame) -> pd.DataFrame:
    """Rank each factor within each timestamp, then sum ranks per asset."""
    ranked = df.copy()
    ranked["rank"] = ranked.groupby(["ts_utc", "factor_name"])["value"].rank(method="average")

    agg = ranked.groupby(["ts_utc", "pair_key"])["rank"].sum().reset_index().rename(columns={"rank": "signal"})
    return _filter_min_assets(agg)


def _filter_min_assets(df: pd.DataFrame, min_assets: int = 3) -> pd.DataFrame:
    """Drop timestamps with fewer than *min_assets* unique pair_keys."""
    counts = df.groupby("ts_utc")["pair_key"].nunique()
    valid_ts = counts[counts >= min_assets].index
    return df[df["ts_utc"].isin(valid_ts)].reset_index(drop=True)


def signal_to_wide(signal_df: pd.DataFrame) -> pd.DataFrame:
    """Pivot long-form signal to wide: index=ts_utc, columns=pair_key, values=signal."""
    return signal_df.pivot(index="ts_utc", columns="pair_key", values="signal")
