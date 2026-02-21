"""
Structural break diagnostics: CUSUM mean-shift and single-break scan (sup-Chow).
Used to flag regime breaks in IC or return series. Research-only.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from .statistics import newey_west_lrv

# Minimum obs for CUSUM (documented)
CUSUM_MIN_OBS = 20
# Minimum obs for single-break scan
SCAN_MIN_OBS = 100


def cusum_mean_shift(
    x: np.ndarray,
    L: Optional[int] = None,
    min_obs: int = CUSUM_MIN_OBS,
) -> Dict[str, Any]:
    """
    CUSUM test for mean shift; variance via HAC (Newey-West).
    Returns stat, p_value (asymptotic), break_suspected (p < 0.05).
    """
    x = np.asarray(x, dtype=float).ravel()
    n = len(x)
    out: Dict[str, Any] = {
        "test_name": "cusum",
        "stat": None,
        "p_value": None,
        "break_suspected": False,
        "estimated_break_index": None,
        "estimated_break_date": None,
        "calibration_method": "HAC",
        "hac_lags_used": None,
        "skipped_reason": None,
    }
    if n < min_obs:
        out["skipped_reason"] = f"n < {min_obs}"
        out["break_suspected"] = False
        return out
    xbar = np.nanmean(x)
    if L is None:
        L = max(0, min(n // 3, int(np.floor(4.0 * (n / 100.0) ** (2.0 / 9.0)))))
    out["hac_lags_used"] = L
    omega = newey_west_lrv(x - xbar, L)
    if omega <= 0 or not np.isfinite(omega):
        out["skipped_reason"] = "non-finite HAC variance"
        out["break_suspected"] = False
        return out
    # CUSUM: S_t = sum_{s=1..t} (x_s - xbar); max normalized by sqrt(omega*n)
    cumsum = np.nancumsum(x - xbar)
    if len(cumsum) < 2:
        return out
    # Standardized CUSUM (scale by sqrt(omega * n))
    scale = np.sqrt(omega * n)
    if scale < 1e-12:
        return out
    cusum_std = np.abs(cumsum) / scale
    stat = float(np.nanmax(cusum_std))
    # Asymptotic distribution of max CUSUM is non-standard; use simple critical value ~1.36 for 5% (one-sided)
    # Approximate p via asymptotic (Brownian bridge): P(max > c) ~ 2 * exp(-2 c^2)
    p = 2.0 * np.exp(-2.0 * stat**2)
    p = min(1.0, max(0.0, float(p)))
    out["stat"] = stat
    out["p_value"] = p
    out["break_suspected"] = p < 0.05
    if out["break_suspected"]:
        out["estimated_break_index"] = int(np.nanargmax(cusum_std))
    out.pop("skipped_reason", None)  # omit when not skipped
    return out


def sup_chow_single_break(
    x: np.ndarray,
    min_obs: int = SCAN_MIN_OBS,
) -> Dict[str, Any]:
    """
    Supremum Chow test: scan over possible break points, maximize Wald/Chow statistic.
    Returns stat, p_value (bootstrap or asymptotic approx), estimated_break_index (argmax).
    """
    x = np.asarray(x, dtype=float).ravel()
    n = len(x)
    out: Dict[str, Any] = {
        "test_name": "sup_chow",
        "stat": None,
        "p_value": None,
        "break_suspected": False,
        "estimated_break_index": None,
        "estimated_break_date": None,
        "calibration_method": "asymptotic",
        "skipped_reason": None,
    }
    if n < min_obs:
        out["skipped_reason"] = f"n < {min_obs}"
        out["break_suspected"] = False
        return out
    # Trim so we have at least 10 obs in each segment
    tau_min, tau_max = 10, n - 10
    if tau_max <= tau_min:
        out["skipped_reason"] = "series too short for scan"
        out["break_suspected"] = False
        return out
    xbar_full = np.nanmean(x)
    ssr_full = np.nansum((x - xbar_full) ** 2)
    if ssr_full < 1e-12:
        out["skipped_reason"] = "degenerate variance (near-constant series)"
        out["break_suspected"] = False
        return out
    best_stat = 0.0
    best_tau = tau_min
    for tau in range(tau_min, tau_max + 1):
        x1 = x[:tau]
        x2 = x[tau:]
        m1 = np.nanmean(x1)
        m2 = np.nanmean(x2)
        ssr1 = np.nansum((x1 - m1) ** 2)
        ssr2 = np.nansum((x2 - m2) ** 2)
        ssr_split = ssr1 + ssr2
        # F-like stat: (SSR_full - SSR_split) / (SSR_split / (n-2))
        ssr_diff = ssr_full - ssr_split
        if ssr_split < 1e-12:
            continue
        f_stat = (ssr_diff / 1.0) / (ssr_split / (n - 2))
        if np.isfinite(f_stat) and f_stat > best_stat:
            best_stat = float(f_stat)
            best_tau = tau
    # Approximate p: sup F under no break (Andrews 1993 style); use simple threshold
    # For 5% approx: critical value for sup F is around 8–10 for many tau
    p = max(0.0, 1.0 - (best_stat / 15.0))  # heuristic
    p = min(1.0, p)
    out["stat"] = best_stat
    out["p_value"] = p
    out["break_suspected"] = p < 0.05
    out["estimated_break_index"] = best_tau
    out.pop("skipped_reason", None)  # omit when not skipped
    return out


def run_break_diagnostics(
    series_dict: Dict[str, pd.Series],
    cusum_min_obs: int = CUSUM_MIN_OBS,
    scan_min_obs: int = SCAN_MIN_OBS,
    hac_lags: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Run CUSUM and sup-Chow on each series in series_dict.
    Returns dict suitable for break_diagnostics.json: series_name -> list of test results.
    """
    results: Dict[str, Any] = {"series": {}, "hac_lags": hac_lags}
    for name, ser in series_dict.items():
        if ser is None or ser.empty:
            continue
        ser_clean = ser.dropna()
        x = ser_clean.values
        if len(x) < 2:
            continue
        index = ser_clean.index

        def break_index_to_date(ix: Optional[int]) -> Optional[str]:
            if ix is None or ix < 0 or ix >= len(index):
                return None
            try:
                if pd.api.types.is_datetime64_any_dtype(index):
                    ts = pd.Timestamp(index[ix])
                    if ts.tz is not None:
                        ts = ts.tz_convert("UTC").tz_localize(None)
                    return ts.strftime("%Y-%m-%dT%H:%M:%S")
            except Exception:
                pass
            return None

        row = []
        cusum_out = cusum_mean_shift(x, L=hac_lags, min_obs=cusum_min_obs)
        if cusum_out.get("estimated_break_index") is not None:
            cusum_out["estimated_break_date"] = break_index_to_date(cusum_out["estimated_break_index"])
        cusum_out["series_name"] = name
        row.append(dict(cusum_out))  # include series_name in each test entry
        scan_out = sup_chow_single_break(x, min_obs=scan_min_obs)
        if scan_out.get("estimated_break_index") is not None:
            scan_out["estimated_break_date"] = break_index_to_date(scan_out["estimated_break_index"])
        scan_out["series_name"] = name
        row.append(dict(scan_out))
        results["series"][name] = row
    return results
