"""
Causal regime features from bars/returns: realized vol, drawdown, trend strength.

All features at time t use only data at or before t (trailing windows). No lookahead.
Convention: decisions at t apply to returns starting t+1; regime at t may use bar at t
as long as it is not applied to decisions executed before bar close. For future
consistency with residualization, an optional as_of_lag_bars (default 1) could be
added to align with factor-model causality; not required for Slice 1.
See docs/spec/components/interfaces.md and phase3_regimes_slice0_alignment.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class RegimeFeatureConfig:
    """Config for building regime features. All windows are trailing (causal)."""

    vol_window: int = 24
    """Rolling window for realized vol (e.g. 24 bars)."""
    drawdown_window: int = 72
    """Window for computing drawdown from cumulative return."""
    trend_window: int = 24
    """Window for trend strength (return over window or slope proxy)."""
    min_bars: int = 12
    """Minimum bars required to compute features; earlier rows get NaN."""


def build_regime_features(
    bars_df: pd.DataFrame,
    config: Optional[RegimeFeatureConfig] = None,
) -> pd.DataFrame:
    """
    Build a DataFrame of causal regime features indexed by ts_utc.

    Expects bars_df to have:
    - column ts_utc (or DatetimeIndex)
    - column log_return or close (to derive returns)
    If multiple rows per ts_utc (long format), market return = mean(log_return) per ts_utc.

    Features (all causal at t, using only <= t data):
    - realized_vol: rolling std of market log_return
    - drawdown: (cummax - cum) / cummax over trailing window
    - trend_strength: sum of log_return over trailing window

    Deterministic: ascending ts_utc, stable column order.
    """
    cfg = config or RegimeFeatureConfig()

    if bars_df.empty:
        return pd.DataFrame(columns=["ts_utc", "realized_vol", "drawdown", "trend_strength"])

    df = bars_df.copy()
    if "ts_utc" not in df.columns and isinstance(df.index, pd.DatetimeIndex):
        df = df.reset_index()
        if len(df.columns) and df.columns[0] == (getattr(df.index, "name", None) or "ts_utc"):
            df = df.rename(columns={df.columns[0]: "ts_utc"})
    if "ts_utc" not in df.columns:
        raise ValueError("bars_df must have ts_utc column or DatetimeIndex")

    ts = pd.to_datetime(df["ts_utc"])
    df = df.assign(ts_utc=ts)

    if "log_return" not in df.columns and "close" in df.columns:
        df["log_return"] = np.log(df["close"] / df["close"].shift(1))
    if "log_return" not in df.columns:
        raise ValueError("bars_df must have log_return or close column")

    # One row per ts_utc: if long format, take mean return per timestamp (market-wide proxy)
    if df["ts_utc"].duplicated().any():
        agg = df.groupby("ts_utc", as_index=False)["log_return"].mean()
        df = agg
    else:
        df = df.sort_values("ts_utc").reset_index(drop=True)

    ret = df["log_return"].astype(float)
    df = df.sort_values("ts_utc").reset_index(drop=True)

    # Realized vol: rolling std of log_return (causal)
    realized_vol = ret.rolling(window=cfg.vol_window, min_periods=cfg.min_bars).std()

    # Drawdown: trailing window; cummax and current level use only past
    cum = (1 + ret).cumprod()
    roll_max = cum.rolling(window=cfg.drawdown_window, min_periods=cfg.min_bars).max()
    drawdown = (roll_max - cum) / np.where(roll_max > 0, roll_max, np.nan)

    # Trend strength: return over trailing window (causal)
    trend_strength = ret.rolling(window=cfg.trend_window, min_periods=cfg.min_bars).sum()

    out = pd.DataFrame(
        {
            "ts_utc": df["ts_utc"],
            "realized_vol": realized_vol.values,
            "drawdown": drawdown.values,
            "trend_strength": trend_strength.values,
        },
        columns=["ts_utc", "realized_vol", "drawdown", "trend_strength"],
    )
    out = out.sort_values("ts_utc").reset_index(drop=True)
    return out
