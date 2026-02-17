"""
Statistical rigor: block bootstrap, confidence intervals, significance.
Research-only; no execution.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .features import bars_per_year, periods_per_year


def block_bootstrap_pnl(
    pnl_series: pd.Series,
    block_size: int,
    n: int = 1000,
    seed: Optional[int] = 42,
) -> np.ndarray:
    """
    Block bootstrap of PnL: resample blocks of size block_size with replacement, compute
    total return (or Sharpe) per resample. Returns distribution of total simple return (1 + r).cumprod()[-1] - 1.
    """
    r = pnl_series.dropna()
    if len(r) < block_size or block_size < 1 or n < 1:
        return np.array([])
    if seed is not None:
        np.random.seed(seed)
    max_start = max(0, len(r) - block_size)
    dist = []
    for _ in range(n):
        indices = []
        while len(indices) < len(r):
            start = np.random.randint(0, max_start + 1) if max_start >= 0 else 0
            end = min(start + block_size, len(r))
            indices.extend(range(start, end))
        indices = indices[: len(r)]
        if len(indices) < 2:
            continue
        resampled = r.iloc[indices]
        cum = (1 + resampled).cumprod()
        total_ret = float(cum.iloc[-1] / cum.iloc[0] - 1.0) if len(cum) > 0 else 0.0
        dist.append(total_ret)
    return np.array(dist)


def sharpe_ci(
    pnl_series: pd.Series,
    freq: str,
    block_size: int,
    n: int = 1000,
    seed: Optional[int] = 42,
    ci_pct: float = 95.0,
) -> Tuple[float, float, float]:
    """
    Block-bootstrap confidence interval for annualized Sharpe ratio.
    Returns (lo, mid, hi). mid = point estimate Sharpe; lo/hi from bootstrap percentiles.
    """
    r = pnl_series.dropna()
    if len(r) < block_size or block_size < 1:
        mid = np.nan
        return (mid, mid, mid)
    bars_yr = bars_per_year(freq)
    mid = float(r.mean() / r.std(ddof=1) * np.sqrt(bars_yr)) if r.std(ddof=1) and r.std(ddof=1) != 0 else np.nan
    if seed is not None:
        np.random.seed(seed)
    max_start = max(0, len(r) - block_size)
    sharpes = []
    for _ in range(n):
        indices = []
        while len(indices) < len(r):
            start = np.random.randint(0, max_start + 1) if max_start >= 0 else 0
            end = min(start + block_size, len(r))
            indices.extend(range(start, end))
        indices = indices[: len(r)]
        resampled = r.iloc[indices]
        if resampled.std(ddof=1) and resampled.std(ddof=1) != 0:
            sh = float(resampled.mean() / resampled.std(ddof=1) * np.sqrt(bars_yr))
            sharpes.append(sh)
    if not sharpes:
        return (mid, mid, mid)
    sharpes = np.array(sharpes)
    lo_pct = (100 - ci_pct) / 2
    hi_pct = 100 - lo_pct
    lo = float(np.percentile(sharpes, lo_pct))
    hi = float(np.percentile(sharpes, hi_pct))
    return (lo, mid, hi)


def reality_check_simple(results_dict: Dict[str, float], threshold: int = 10) -> Optional[str]:
    """
    Simple warning: if more than threshold strategies are tested without multiple-testing correction,
    returns a warning message. Otherwise returns None.
    """
    if len(results_dict) > threshold:
        return (
            f"Reality check: {len(results_dict)} strategies tested. Consider multiple-testing correction (e.g. Bonferroni, FDR)."
        )
    return None


def significance_summary(
    pnl_series: pd.Series,
    freq: str,
    block_size: Optional[int] = None,
    n_bootstrap: int = 1000,
) -> Dict[str, float]:
    """
    Summary: annualized Sharpe, approximate t-stat (Sharpe * sqrt(n)), and bootstrap 95% CI for Sharpe.
    block_size default: sqrt(n_obs) or 20, whichever is larger (common heuristic).
    """
    r = pnl_series.dropna()
    n = len(r)
    if n < 2:
        return {"sharpe_annual": np.nan, "t_stat_approx": np.nan, "sharpe_ci_95_lo": np.nan, "sharpe_ci_95_hi": np.nan}
    bars_yr = bars_per_year(freq)
    vol = r.std(ddof=1)
    sharpe_annual = float(r.mean() / vol * np.sqrt(bars_yr)) if vol and vol != 0 else np.nan
    t_stat_approx = sharpe_annual * np.sqrt(n) if pd.notna(sharpe_annual) else np.nan
    block_size = block_size or max(20, int(np.sqrt(n)))
    lo, mid, hi = sharpe_ci(pnl_series, freq, block_size=block_size, n=n_bootstrap)
    return {
        "sharpe_annual": sharpe_annual,
        "t_stat_approx": float(t_stat_approx) if pd.notna(t_stat_approx) else np.nan,
        "sharpe_ci_95_lo": lo,
        "sharpe_ci_95_hi": hi,
    }
