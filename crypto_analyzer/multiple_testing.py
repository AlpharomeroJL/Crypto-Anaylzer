"""
Overfitting defenses: Deflated Sharpe, White's Reality Check style warning, PBO proxy.
Research-only. See docs for disclaimers.
"""

from __future__ import annotations

import math
from typing import Any, Dict

import numpy as np
import pandas as pd


def deflated_sharpe_ratio(
    pnl_series: pd.Series,
    freq: str,
    n_trials_estimate: int,
    skew_kurtosis_optional: bool = True,
) -> Dict[str, Any]:
    """
    Deflated Sharpe Ratio (DSR) style adjustment for multiple testing / selection bias.
    Uses approximate formula: E[max SR under null] and variance of SR estimator;
    returns dict with deflated_sr, raw_sr, n_obs, and optional skew/kurtosis if available.

    WARNING: Assumptions are rough (e.g. iid returns, normality of SR estimator).
    Use for research screening only, not for sole inference.
    """
    if pnl_series.empty or len(pnl_series.dropna()) < 10:
        return {
            "deflated_sr": np.nan,
            "raw_sr": np.nan,
            "n_obs": 0,
            "n_trials": n_trials_estimate,
            "message": "Insufficient data",
        }
    pnl = pnl_series.dropna()
    n = len(pnl)
    mean_ret = float(pnl.mean())
    std_ret = float(pnl.std(ddof=1))
    if std_ret < 1e-12:
        return {
            "deflated_sr": np.nan,
            "raw_sr": np.nan,
            "n_obs": n,
            "n_trials": n_trials_estimate,
            "message": "Zero variance",
        }
    raw_sr = mean_ret / std_ret
    # Variance of Sharpe estimator (under iid): V[SR] ≈ (1 + 0.5*SR^2 - skew*SR + (kurt-3)/4*SR^2) / n
    try:
        skew = float(pnl.skew()) if skew_kurtosis_optional else 0.0
        kurt = float(pnl.kurtosis()) if skew_kurtosis_optional else 0.0  # excess kurtosis
    except Exception:
        skew, kurt = 0.0, 0.0
    var_sr = (1.0 + 0.5 * raw_sr**2 - skew * raw_sr + (kurt / 4.0) * raw_sr**2) / n
    var_sr = max(var_sr, 1e-12)
    std_sr = math.sqrt(var_sr)
    # E[max SR] under null (N iid trials): approximation E[max] ≈ sqrt(V[SR]) * sqrt(2*log(N))
    # Bailey-López de Prado use Z(1-1/N) term; we use a simple sqrt(2*ln(N)) approximation.
    N = max(n_trials_estimate, 1)
    e_max_sr = std_sr * math.sqrt(2.0 * math.log(N))
    deflated_sr = (raw_sr - e_max_sr) / std_sr if std_sr > 1e-12 else np.nan
    if not np.isfinite(deflated_sr):
        deflated_sr = np.nan
    return {
        "deflated_sr": float(deflated_sr),
        "raw_sr": float(raw_sr),
        "n_obs": n,
        "n_trials": N,
        "var_sr_est": var_sr,
        "e_max_sr_null": e_max_sr,
        "skew": skew,
        "excess_kurtosis": kurt,
    }


def reality_check_warning(
    num_signals_tested: int,
    num_portfolios_tested: int,
) -> str:
    """
    Message with suggested controls when many signals/portfolios were tested
    (White's Reality Check style: avoid overfitting to best outcome).
    """
    parts = [
        "Multiple testing: you tested %d signals and %d portfolios." % (num_signals_tested, num_portfolios_tested),
    ]
    if num_signals_tested > 5 or num_portfolios_tested > 5:
        parts.append(
            "Suggested controls: use deflated Sharpe, out-of-sample / walk-forward, "
            "and avoid selecting the single best backtest without robustness checks."
        )
    if num_signals_tested > 20 or num_portfolios_tested > 20:
        parts.append("Consider Bonferroni or FDR correction on p-values, or report median performance across variants.")
    return " ".join(parts)


def pbo_proxy_walkforward(results_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Probability of Backtest Overfitting (PBO) proxy from walk-forward results.
    results_df should have columns including split identifier, train metric, test metric
    (e.g. 'split_id', 'train_sharpe', 'test_sharpe' or 'train_pnl', 'test_pnl').
    PBO proxy = fraction of splits where the strategy chosen as best in train underperforms
    the median in test.
    """
    if results_df is None or results_df.empty:
        return {"pbo_proxy": np.nan, "n_splits": 0, "explanation": "No walk-forward results."}
    # Try common column names
    split_col = None
    for c in ["split_id", "split", "fold"]:
        if c in results_df.columns:
            split_col = c
            break
    if split_col is None:
        # Single column of test metrics: treat each row as a split
        split_col = "_row_"
        results_df = results_df.copy()
        results_df[split_col] = range(len(results_df))

    train_col = None
    test_col = None
    for a, b in [("train_sharpe", "test_sharpe"), ("train_pnl", "test_pnl"), ("train_ret", "test_ret")]:
        if a in results_df.columns and b in results_df.columns:
            train_col, test_col = a, b
            break
    if train_col is None or test_col is None:
        return {
            "pbo_proxy": np.nan,
            "n_splits": len(results_df),
            "explanation": "Need columns train_sharpe/test_sharpe or train_pnl/test_pnl.",
        }

    splits = results_df[split_col].unique()
    n_splits = len(splits)
    if n_splits < 2:
        return {"pbo_proxy": np.nan, "n_splits": n_splits, "explanation": "Too few splits for PBO."}

    # For each split we have one row (one strategy chosen as best in train). So we don't have
    # "chosen best in train" explicitly; assume each row is the selected strategy for that split.
    # PBO = P(test performance of selected strategy < median test performance across splits)
    test_vals = results_df[test_col].dropna()
    if len(test_vals) < 2:
        return {"pbo_proxy": np.nan, "n_splits": n_splits, "explanation": "Insufficient test metrics."}
    median_test = test_vals.median()
    underperform = (results_df[test_col] < median_test).sum()
    pbo = underperform / len(results_df)
    return {
        "pbo_proxy": float(pbo),
        "n_splits": int(n_splits),
        "median_test": float(median_test),
        "explanation": (
            "Fraction of splits where the strategy (best in train) underperformed "
            "median test metric. High PBO suggests backtest overfitting."
        ),
    }
