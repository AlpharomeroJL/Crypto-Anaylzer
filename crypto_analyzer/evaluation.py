"""
Regime-conditioned performance and stability. Research-only.
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd


def conditional_metrics(
    pnl_series: pd.Series,
    regime_series: pd.Series,
) -> pd.DataFrame:
    """
    Metrics by regime bucket: Sharpe, CAGR proxy, max DD, hit rate, avg daily pnl, n.
    regime_series: same index as pnl (or aligned); values are regime labels.
    """
    if pnl_series.empty:
        return pd.DataFrame()
    common = pnl_series.index.intersection(regime_series.index)
    if len(common) == 0:
        return pd.DataFrame()
    pnl = pnl_series.loc[common].dropna()
    regime = regime_series.loc[common].reindex(pnl.index).ffill().bfill()
    regime = regime.fillna("unknown")
    rows = []
    for r in regime.unique():
        mask = regime == r
        p = pnl[mask]
        if len(p) < 2:
            rows.append(
                {
                    "regime": r,
                    "sharpe": np.nan,
                    "cagr_proxy": np.nan,
                    "max_dd": np.nan,
                    "hit_rate": np.nan,
                    "avg_daily_pnl": np.nan,
                    "n": len(p),
                }
            )
            continue
        mean = p.mean()
        std = p.std()
        sharpe = (mean / std) if std and std > 1e-12 else np.nan
        # CAGR proxy: (1 + mean)^periods_per_year - 1 (if pnl is per-period return)
        cagr = (1.0 + mean) ** 252 - 1.0 if mean > -1 else np.nan  # rough daily proxy
        cum = (1 + p).cumprod()
        peak = cum.cummax()
        dd = cum / peak - 1.0
        max_dd = dd.min() if len(dd) else np.nan
        hit_rate = (p > 0).mean() if len(p) else np.nan
        rows.append(
            {
                "regime": r,
                "sharpe": float(sharpe),
                "cagr_proxy": float(cagr),
                "max_dd": float(max_dd),
                "hit_rate": float(hit_rate),
                "avg_daily_pnl": float(mean),
                "n": int(len(p)),
            }
        )
    return pd.DataFrame(rows)


def stability_report(
    ic_ts: pd.Series,
    pnl_ts: pd.Series,
    rolling_window: int = 252,
) -> dict:
    """
    Rolling Sharpe, rolling IC mean, drawdown duration, fragility score
    (% months negative + worst rolling window).
    """
    out = {}
    if pnl_ts.empty:
        return out
    pnl = pnl_ts.dropna()
    if len(pnl) < 2:
        return out
    # Rolling Sharpe (annualized proxy)
    roll_mean = pnl.rolling(rolling_window).mean()
    roll_std = pnl.rolling(rolling_window).std(ddof=1)
    roll_sharpe = (roll_mean / roll_std).replace([np.inf, -np.inf], np.nan)
    out["rolling_sharpe"] = roll_sharpe
    out["rolling_sharpe_mean"] = float(roll_sharpe.mean()) if roll_sharpe.notna().any() else np.nan

    if not ic_ts.empty:
        ic = ic_ts.reindex(pnl.index).dropna()
        if len(ic) >= rolling_window:
            out["rolling_ic_mean"] = float(ic.rolling(rolling_window).mean().mean())
        else:
            out["rolling_ic_mean"] = float(ic.mean()) if len(ic) else np.nan

    # Drawdown duration: length of runs where cumulative return is below peak
    cum = (1 + pnl).cumprod()
    peak = cum.cummax()
    in_dd = cum < peak
    # Count consecutive True
    grp = (~in_dd).cumsum()
    dd_durations = in_dd.groupby(grp).sum()
    out["max_drawdown_duration_bars"] = int(dd_durations.max()) if len(dd_durations) else 0

    # Fragility: % months negative (if index is datetime) or % of rolling windows negative
    roll_sum = pnl.rolling(rolling_window).sum()
    try:
        monthly = pnl.resample("M").sum()
        pct_neg_months = (monthly < 0).mean() if len(monthly) else np.nan
    except Exception:
        pct_neg_months = (roll_sum < 0).mean() if roll_sum.notna().any() else np.nan
    out["pct_negative_months"] = float(pct_neg_months) if np.isfinite(pct_neg_months) else np.nan
    worst_roll = float(roll_sum.min()) if roll_sum.notna().any() else np.nan
    out["worst_rolling_window_pnl"] = worst_roll
    pct = float(pct_neg_months) if np.isfinite(pct_neg_months) else 0.0
    out["fragility_score"] = (pct + (1.0 if (np.isfinite(worst_roll) and worst_roll < 0) else 0.0)) / 2.0
    return out


def lead_lag_analysis(
    signal_df: pd.DataFrame,
    returns_df: pd.DataFrame,
    lags: Optional[List[int]] = None,
) -> pd.Series:
    """
    Correlation of signal with forward/backward returns at each lag (1h bars default).
    lags: e.g. list(range(-24, 25)); negative = signal leads return (corr(signal[t], return[t+|lag|])).
    Works with small universes; uses aligned (time, asset) pairs.
    """
    if lags is None:
        lags = list(range(-24, 25))
    if signal_df.empty or returns_df.empty:
        return pd.Series(dtype=float)
    common_idx = signal_df.index.intersection(returns_df.index)
    if len(common_idx) < 2:
        return pd.Series(dtype=float)
    cols = signal_df.columns.intersection(returns_df.columns)
    if len(cols) == 0:
        return pd.Series(dtype=float)
    sig = signal_df.loc[common_idx, cols]
    ret = returns_df.loc[common_idx, cols]
    result = {}
    for lag in lags:
        if lag < 0:
            # signal leads: corr(signal[t], return[t+|lag|]) -> need return at t+|lag| at index t
            ret_shifted = ret.shift(lag)  # shift(-24) puts return[t+24] at index t
        elif lag > 0:
            ret_shifted = ret.shift(lag)  # shift(24) puts return[t-24] at index t
        else:
            ret_shifted = ret
        common = sig.index.intersection(ret_shifted.index)
        s = sig.loc[common, cols].values.ravel()
        r = ret_shifted.loc[common, cols].values.ravel()
        valid = np.isfinite(s) & np.isfinite(r)
        if valid.sum() < 10:
            result[lag] = np.nan
            continue
        s, r = s[valid], r[valid]
        c = np.corrcoef(s, r)[0, 1] if np.std(s) > 1e-12 and np.std(r) > 1e-12 else np.nan
        result[lag] = float(c) if np.isfinite(c) else np.nan
    return pd.Series(result)
