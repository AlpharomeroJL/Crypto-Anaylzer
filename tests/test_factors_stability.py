"""
Numerical stability of OLS factor model: singular/collinear X'X, no crashes.
fit_ols, compute_ols_betas, rolling/causal OLS use robust solve (lstsq/ridge fallback).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.factors import (
    causal_rolling_ols,
    compute_ols_betas,
    fit_ols,
    rolling_multifactor_ols,
)


class TestFitOlsStability:
    """fit_ols must not crash on ill-conditioned or singular X'X."""

    def test_singular_matrix_no_crash(self):
        # X has two identical columns -> X'X singular
        np.random.seed(1)
        n = 50
        x = np.random.randn(n) * 0.01
        X = np.column_stack([x, x])  # rank 1
        y = np.random.randn(n) * 0.001
        betas, intercept, r2 = fit_ols(X, y, add_const=True)
        # Should return NaN or finite values from fallback, never raise
        assert betas.shape == (2,)
        assert np.any(np.isnan(betas)) or np.all(np.isfinite(betas))

    def test_collinear_factors_ridge_fallback(self):
        # Slightly perturbed second column -> very ill-conditioned
        np.random.seed(2)
        n = 100
        x1 = np.random.randn(n) * 0.01
        x2 = x1 + np.random.randn(n) * 1e-8
        X = np.column_stack([x1, x2])
        y = 0.5 * x1 + np.random.randn(n) * 0.001
        betas, intercept, r2 = fit_ols(X, y, add_const=True)
        assert betas.shape == (2,)
        # Either NaN (rejected) or finite (ridge gave something)
        assert np.any(np.isnan(betas)) or np.all(np.isfinite(betas))

    def test_constant_regressor_no_crash(self):
        # One factor is constant -> singular with intercept
        n = 30
        X = np.column_stack([np.ones(n) * 0.01, np.random.randn(n) * 0.01])
        y = np.random.randn(n) * 0.001
        betas, intercept, r2 = fit_ols(X, y, add_const=True)
        assert betas.shape == (2,)

    def test_single_row_returns_nan(self):
        X = np.array([[1.0, 2.0]])
        y = np.array([1.0])
        betas, intercept, r2 = fit_ols(X, y, add_const=True)
        assert np.all(np.isnan(betas)) or betas.shape == (2,)
        assert np.isnan(intercept)
        assert np.isnan(r2)


class TestComputeOlsBetasStability:
    """compute_ols_betas uses robust solve; no crash on singular."""

    def test_singular_returns_empty_or_nan(self):
        idx = pd.date_range("2024-01-01", periods=20, freq="h")
        # Same series twice -> singular
        f = pd.Series(np.random.randn(20) * 0.01, index=idx)
        X = pd.DataFrame({"A": f, "B": f}, index=idx)
        y = pd.Series(np.random.randn(20) * 0.001, index=idx)
        betas, alpha = compute_ols_betas(y, X)
        assert len(betas) == 0 or np.any(np.isnan(betas)) or np.all(np.isfinite(betas))
        assert np.isnan(alpha) or np.isfinite(alpha)


class TestRollingCausalStability:
    """Rolling and causal OLS should not crash on collinear factor windows."""

    def test_rolling_collinear_factors_no_crash(self):
        np.random.seed(3)
        n = 80
        idx = pd.date_range("2024-01-01", periods=n, freq="h")
        btc = np.random.randn(n) * 0.01
        # ETH = BTC (collinear)
        eth = btc.copy()
        asset = 1.0 * btc + np.random.randn(n) * 0.002
        returns_df = pd.DataFrame({"BTC_spot": btc, "ETH_spot": eth, "A": asset}, index=idx)
        factor_df = returns_df[["BTC_spot", "ETH_spot"]]
        betas_dict, r2_df, residual_df = rolling_multifactor_ols(returns_df, factor_df, window=24, min_obs=12)
        assert "BTC_spot" in betas_dict
        assert "ETH_spot" in betas_dict
        # Some NaNs expected in collinear windows; no exception
        _ = betas_dict["BTC_spot"]["A"]

    def test_causal_collinear_no_crash(self):
        np.random.seed(4)
        n = 60
        idx = pd.date_range("2024-06-01", periods=n, freq="h")
        btc = np.random.randn(n) * 0.01
        eth = btc + np.random.randn(n) * 1e-10  # nearly identical
        asset = 0.5 * btc + np.random.randn(n) * 0.001
        df = pd.DataFrame({"BTC_spot": btc, "ETH_spot": eth, "A": asset}, index=idx)
        betas_dict, r2_df, residual_df, alpha_df = causal_rolling_ols(
            df, factor_cols=["BTC_spot", "ETH_spot"], window_bars=20, min_obs=10, as_of_lag_bars=1
        )
        assert "BTC_spot" in betas_dict
        assert "ETH_spot" in betas_dict
        # No crash; may have NaNs where solve was ill-conditioned
        _ = residual_df["A"].dropna()
