"""
Statistical rigor: block bootstrap (fixed and stationary), confidence intervals, significance.
Research-only; no execution.
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional, Tuple

import numpy as np
import pandas as pd

from .features import bars_per_year


def _stationary_bootstrap_indices(
    length: int,
    avg_block_length: float,
    seed: Optional[int],
) -> np.ndarray:
    """
    Politis-Romano stationary bootstrap: geometric block lengths with mean avg_block_length.
    p = 1 / avg_block_length. Returns indices of length `length` (wraps around).
    """
    if length < 1 or avg_block_length < 1:
        return np.array([], dtype=int)
    if seed is not None:
        np.random.seed(seed)
    p = 1.0 / avg_block_length
    indices = []
    while len(indices) < length:
        block_len = np.random.geometric(p)
        if block_len < 1:
            block_len = 1
        start = np.random.randint(0, length)
        for _ in range(block_len):
            indices.append(start % length)
            start += 1
            if len(indices) >= length:
                break
    return np.array(indices[:length], dtype=int)


def block_bootstrap_pnl(
    pnl_series: pd.Series,
    block_size: int,
    n: int = 1000,
    seed: Optional[int] = 42,
    method: Literal["block_fixed", "stationary"] = "block_fixed",
    avg_block_length: Optional[float] = None,
) -> np.ndarray:
    """
    Block bootstrap of PnL: resample blocks with replacement, compute total return per resample.
    method: "block_fixed" = fixed block size; "stationary" = Politis-Romano (geometric block lengths).
    For stationary, avg_block_length is used (default = block_size). seed required for determinism.
    Returns distribution of total simple return (1 + r).cumprod()[-1] - 1.
    """
    r = pnl_series.dropna()
    L = len(r)
    if method == "stationary":
        avg = avg_block_length if avg_block_length is not None else float(block_size)
        if L < 2 or avg < 1 or n < 1:
            return np.array([])
        dist = []
        for _ in range(n):
            idx = _stationary_bootstrap_indices(L, avg, seed)
            if len(idx) < 2:
                continue
            resampled = r.iloc[idx].values
            cum = np.cumprod(1.0 + resampled)
            total_ret = float(cum[-1] / cum[0] - 1.0) if len(cum) > 0 else 0.0
            dist.append(total_ret)
        return np.array(dist)
    if L < block_size or block_size < 1 or n < 1:
        return np.array([])
    if seed is not None:
        np.random.seed(seed)
    max_start = max(0, L - block_size)
    dist = []
    for _ in range(n):
        indices = []
        while len(indices) < L:
            start = np.random.randint(0, max_start + 1) if max_start >= 0 else 0
            end = min(start + block_size, L)
            indices.extend(range(start, end))
        indices = indices[:L]
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
    method: Literal["block_fixed", "stationary"] = "block_fixed",
    avg_block_length: Optional[float] = None,
) -> Tuple[float, float, float]:
    """
    Block-bootstrap confidence interval for annualized Sharpe ratio.
    method: "block_fixed" or "stationary". seed required for determinism.
    Returns (lo, mid, hi). mid = point estimate Sharpe; lo/hi from bootstrap percentiles.
    """
    r = pnl_series.dropna()
    L = len(r)
    bars_yr = bars_per_year(freq)
    mid = (
        float(r.mean() / r.std(ddof=1) * np.sqrt(bars_yr))
        if L >= 2 and r.std(ddof=1) and r.std(ddof=1) != 0
        else np.nan
    )
    if method == "stationary":
        avg = avg_block_length if avg_block_length is not None else float(block_size)
        if L < 2 or avg < 1:
            return (mid, mid, mid)
        sharpes = []
        for _ in range(n):
            idx = _stationary_bootstrap_indices(L, avg, seed)
            resampled = r.iloc[idx]
            if resampled.std(ddof=1) and resampled.std(ddof=1) != 0:
                sh = float(resampled.mean() / resampled.std(ddof=1) * np.sqrt(bars_yr))
                sharpes.append(sh)
    else:
        if L < block_size or block_size < 1:
            return (mid, mid, mid)
        if seed is not None:
            np.random.seed(seed)
        max_start = max(0, L - block_size)
        sharpes = []
        for _ in range(n):
            indices = []
            while len(indices) < L:
                start = np.random.randint(0, max_start + 1) if max_start >= 0 else 0
                end = min(start + block_size, L)
                indices.extend(range(start, end))
            indices = indices[:L]
            resampled = r.iloc[indices]
            if resampled.std(ddof=1) and resampled.std(ddof=1) != 0:
                sh = float(resampled.mean() / resampled.std(ddof=1) * np.sqrt(bars_yr))
                sharpes.append(sh)
    if not sharpes:
        return (mid, mid, mid)
    sharpes_arr = np.array(sharpes)
    lo_pct = (100 - ci_pct) / 2
    hi_pct = 100 - lo_pct
    lo = float(np.percentile(sharpes_arr, lo_pct))
    hi = float(np.percentile(sharpes_arr, hi_pct))
    return (lo, mid, hi)


def reality_check_simple(results_dict: Dict[str, float], threshold: int = 10) -> Optional[str]:
    """
    Simple warning: if more than threshold strategies are tested without multiple-testing correction,
    returns a warning message. Otherwise returns None.
    """
    if len(results_dict) > threshold:
        return f"Reality check: {len(results_dict)} strategies tested. Consider multiple-testing correction (e.g. Bonferroni, FDR)."
    return None


def significance_summary(
    pnl_series: pd.Series,
    freq: str,
    block_size: Optional[int] = None,
    n_bootstrap: int = 1000,
    seed: Optional[int] = 42,
    method: Literal["block_fixed", "stationary"] = "block_fixed",
    avg_block_length: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Summary: annualized Sharpe, approximate t-stat, and bootstrap 95% CI for Sharpe.
    block_size default: sqrt(n_obs) or 20 (for block_fixed). method/seed/block_length
    in output for artifact metadata.
    """
    r = pnl_series.dropna()
    n = len(r)
    if n < 2:
        return {
            "sharpe_annual": np.nan,
            "t_stat_approx": np.nan,
            "sharpe_ci_95_lo": np.nan,
            "sharpe_ci_95_hi": np.nan,
            "bootstrap_method": method,
            "bootstrap_seed": seed,
            "block_length": block_size or 20,
        }
    bars_yr = bars_per_year(freq)
    vol = r.std(ddof=1)
    sharpe_annual = float(r.mean() / vol * np.sqrt(bars_yr)) if vol and vol != 0 else np.nan
    t_stat_approx = sharpe_annual * np.sqrt(n) if pd.notna(sharpe_annual) else np.nan
    blk = block_size or max(20, int(np.sqrt(n)))
    avg_blk = avg_block_length if avg_block_length is not None else float(blk)
    lo, mid, hi = sharpe_ci(
        pnl_series,
        freq,
        block_size=blk,
        n=n_bootstrap,
        seed=seed,
        method=method,
        avg_block_length=avg_blk if method == "stationary" else None,
    )
    return {
        "sharpe_annual": sharpe_annual,
        "t_stat_approx": float(t_stat_approx) if pd.notna(t_stat_approx) else np.nan,
        "sharpe_ci_95_lo": lo,
        "sharpe_ci_95_hi": hi,
        "bootstrap_method": method,
        "bootstrap_seed": seed,
        "block_length": blk if method == "block_fixed" else avg_blk,
    }


def safe_nanmean(values) -> Optional[float]:
    """Return float nanmean, or None when *values* is empty / all-NaN.

    Avoids the numpy RuntimeWarning 'Mean of empty slice' that fires when
    every element is NaN or the input is length-zero.
    """
    if values is None:
        return None
    arr = np.asarray(values, dtype=float)
    if arr.size == 0 or np.all(np.isnan(arr)):
        return None
    return float(np.nanmean(arr))
