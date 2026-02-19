"""
Causal regime features from bars/returns: realized vol, drawdown, trend strength.

All features at time t use only data at or before t (trailing windows). No lookahead.
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
    - index or column ts_utc (datetime or str)
    - column log_return or close (to derive returns)

    Features (all causal at t, using only <= t data):
    - realized_vol: rolling std of log_return (or EWMA of squared returns)
    - drawdown: (cummax - cum) / cummax over trailing window
    - trend_strength: (close_t - close_t_window) / close_t_window or return over window

    Deterministic: ascending ts_utc, stable column order.
    """
    cfg = config or RegimeFeatureConfig()
    out: pd.DataFrame

    if bars_df.empty:
        return pd.DataFrame(columns=["ts_utc", "realized_vol", "drawdown", "trend_strength"])

    df = bars_df.copy()
    if "ts_utc" not in df.columns and isinstance(df.index, pd.DatetimeIndex):
        df = df.reset_index()
        if df.index.name and df.columns[0] == df.index.name:
            df = df.rename(columns={df.columns[0]: "ts_utc"})
    if "ts_utc" not in df.columns:
        raise ValueError("bars_df must have ts_utc column or DatetimeIndex")

    ts = pd.to_datetime(df["ts_utc"])
    df = df.assign(ts_utc=ts).sort_values("ts_utc").reset_index(drop=True)

    if "log_return" not in df.columns and "close" in df.columns:
        df["log_return"] = np.log(df["close"] / df["close"].shift(1))
    if "log_return" not in df.columns:
        raise ValueError("bars_df must have log_return or close column")

    ret = df["log_return"].astype(float)
    n = len(df)

    # Realized vol: rolling std of log_return (causal)
    realized_vol = ret.rolling(window=cfg.vol_window, min_periods=cfg.min_bars).std()

    # Drawdown: trailing window; cummax and current level use only past
    cum = (1 + ret).cumprod()
    roll_max = cum.rolling(window=cfg.drawdown_window, min_periods=cfg.min_bars).max()
    drawdown = (roll_max - cum) / np.where(roll_max > 0, roll_max, np.nan)

    # Trend strength: return over trailing window (causal)
    roll_sum = ret.rolling(window=cfg.trend_window, min_periods=cfg.min_bars).sum()
    trend_strength = roll_sum  # or (close_t - close_t_n) / close_t_n

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
