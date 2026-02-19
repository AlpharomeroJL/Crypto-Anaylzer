"""
Diagnostics: fragility, stability, parameter sensitivity, regime concentration.
Research-only. All functions degrade gracefully with small universes.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import numpy as np
import pandas as pd


def rolling_ic_stability(
    ic_series: pd.Series,
    window: int,
) -> dict:
    """
    Compute mean, std, and stability_score (mean/std clipped) of rolling IC.
    Returns dict with mean, std, stability_score.
    """
    out = {"mean": np.nan, "std": np.nan, "stability_score": np.nan}
    if ic_series is None or ic_series.empty or window < 2:
        return out
    clean = ic_series.dropna()
    if len(clean) < window:
        out["mean"] = float(clean.mean()) if len(clean) else np.nan
        out["std"] = float(clean.std()) if len(clean) >= 2 else np.nan
        return out
    roll = clean.rolling(window).mean()
    roll_std = clean.rolling(window).std()
    out["mean"] = float(roll.iloc[-1])
    out["std"] = float(roll_std.iloc[-1]) if not pd.isna(roll_std.iloc[-1]) else np.nan
    if out["std"] and out["std"] > 0:
        out["stability_score"] = float(np.clip(out["mean"] / out["std"], -10, 10))
    return out


def parameter_sensitivity_smoke(
    report_fn: Callable[..., Any],
    base_args: dict,
    grid_args: dict,
) -> pd.DataFrame:
    """
    Run report_fn with base_args and one varying arg from grid_args (small smoke grid).
    grid_args should be like {"freq": ["1h", "5min"]} - not huge.
    Returns DataFrame with columns for each grid dimension and key outputs if available.
    """
    rows = []
    keys = list(grid_args.keys())
    if not keys:
        return pd.DataFrame()

    def _recursive_grid(idx: int, current: dict) -> None:
        if idx >= len(keys):
            try:
                report_fn(**{**base_args, **current})
                rows.append({**current, "status": "ok"})
            except Exception as e:
                rows.append({**current, "status": "error", "error": str(e)[:200]})
            return
        key = keys[idx]
        for v in grid_args[key][:5]:  # cap 5 per dimension
            _recursive_grid(idx + 1, {**current, key: v})

    _recursive_grid(0, {})
    return pd.DataFrame(rows)


def regime_concentration(
    perf_df: pd.DataFrame,
    regime_col: str = "regime",
) -> pd.DataFrame:
    """
    Count or aggregate performance by regime. perf_df should have regime_col and numeric cols.
    Returns summary DataFrame (e.g. count per regime, mean return per regime).
    """
    if perf_df is None or perf_df.empty or regime_col not in perf_df.columns:
        return pd.DataFrame()
    g = perf_df.groupby(regime_col)
    count = g.size().to_frame("n")
    numeric = perf_df.select_dtypes(include=[np.number])
    if not numeric.empty:
        means = g[numeric.columns].mean()
        return count.join(means, how="left")
    return count


def asset_concentration(weights_df: pd.DataFrame) -> dict:
    """
    Compute max weight and Herfindahl index. weights_df: index=time, columns=assets, values=weights.
    """
    out = {"max_weight": np.nan, "herfindahl": np.nan}
    if weights_df is None or weights_df.empty:
        return out
    w = weights_df.abs()
    out["max_weight"] = float(w.max().max()) if w.size else np.nan
    try:
        # Herfindahl: sum of squared weights (per row then average or last)
        h = (w**2).sum(axis=1)
        out["herfindahl"] = float(h.iloc[-1]) if len(h) else np.nan
    except Exception:
        pass
    return out


def cost_sensitivity(
    pnl_gross: pd.Series,
    pnl_net: pd.Series,
) -> dict:
    """Compute cost drag (gross - net) and percent drag."""
    out = {"drag": np.nan, "percent": np.nan}
    if pnl_gross is None or pnl_net is None or pnl_gross.empty or pnl_net.empty:
        return out
    common = pnl_gross.align(pnl_net, join="inner")
    g = common[0].dropna()
    n = common[1].reindex(g.index).ffill().bfill()
    if len(g) < 2:
        return out
    gross_total = (1 + g).prod() - 1.0
    net_total = (1 + n).prod() - 1.0
    out["drag"] = float(gross_total - net_total)
    out["percent"] = float((out["drag"] / gross_total * 100) if gross_total and abs(gross_total) > 1e-12 else 0)
    return out


def build_health_summary(
    data_coverage: Optional[dict] = None,
    signal_stability: Optional[dict] = None,
    overfitting_risk_proxies: Optional[dict] = None,
    regime_dependency: Optional[dict] = None,
    capacity_proxy: Optional[dict] = None,
) -> dict:
    """
    Build a single health summary dict from optional component dicts.
    All inputs optional; missing keys omitted. Degrades gracefully.
    """
    out: dict = {}
    if data_coverage is not None:
        out["data_coverage"] = data_coverage
    if signal_stability is not None:
        out["signal_stability"] = signal_stability
    if overfitting_risk_proxies is not None:
        out["overfitting_risk_proxies"] = overfitting_risk_proxies
    if regime_dependency is not None:
        out["regime_dependency"] = regime_dependency
    if capacity_proxy is not None:
        out["capacity_proxy"] = capacity_proxy
    return out
