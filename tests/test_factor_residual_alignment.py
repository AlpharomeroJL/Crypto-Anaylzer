"""Factor/residual alignment: residuals computed and aligned when both factors exist."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.factors import (
    build_factor_matrix,
    compute_ols_betas,
    compute_residual_lookback_return,
    compute_residual_returns,
    compute_residual_vol,
)


def test_build_factor_matrix_aligns_index():
    """Factor matrix has aligned index (no NaN in factor rows)."""
    idx = pd.date_range("2024-01-01", periods=100, freq="1h")
    df = pd.DataFrame(
        {"BTC_spot": np.random.randn(100).cumsum() * 0.01, "ETH_spot": np.random.randn(100).cumsum() * 0.01},
        index=idx,
    )
    X = build_factor_matrix(df, factor_cols=["BTC_spot", "ETH_spot"])
    assert not X.empty
    assert X.index.is_monotonic_increasing or len(X) == 1
    assert list(X.columns) == ["BTC_spot", "ETH_spot"]
    assert X.isna().sum().sum() == 0


def test_residuals_aligned_when_both_factors_exist():
    """Residual series index is aligned with asset and factor index (intersection)."""
    np.random.seed(43)
    n = 80
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    btc = np.random.randn(n) * 0.01
    eth = np.random.randn(n) * 0.01
    asset = 0.6 * btc + 0.2 * eth + np.random.randn(n) * 0.005
    returns_df = pd.DataFrame(
        {"pair1": asset, "BTC_spot": btc, "ETH_spot": eth},
        index=idx,
    )
    X = build_factor_matrix(returns_df, factor_cols=["BTC_spot", "ETH_spot"])
    y = returns_df["pair1"]
    betas, intercept = compute_ols_betas(y, X)
    assert len(betas) == 2
    resid = compute_residual_returns(y, X, betas, float(intercept))
    assert len(resid) > 0
    assert resid.index.isin(returns_df.index).all()
    assert resid.index.isin(X.index).all()


def test_residual_lookback_and_vol_use_aligned_series():
    """compute_residual_lookback_return and compute_residual_vol work on aligned residual series."""
    np.random.seed(44)
    n = 50
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    resid = pd.Series(np.random.randn(n) * 0.01, index=idx)
    lookback = 24
    r = compute_residual_lookback_return(resid, lookback)
    assert not np.isnan(r) or (resid.dropna().tail(lookback).size < lookback)
    vol = compute_residual_vol(resid, lookback, "1h")
    assert vol is np.nan or vol >= 0
