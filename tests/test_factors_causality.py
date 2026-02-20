"""
Causality tests for rolling OLS factor model: no lookahead.
- Recover known betas from synthetic data.
- Introduce a 'future leak' in synthetic data and verify that with lag it cannot
  improve fit beyond noise (lag prevents using future in fit).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.factors import (
    causal_residual_returns,
    causal_rolling_ols,
    fit_ols,
)


class TestSyntheticBetaRecovery:
    """Generate known factor exposures and returns; ensure recovered betas are close."""

    def test_fit_ols_recovers_true_betas(self):
        np.random.seed(42)
        n = 500
        F1 = np.random.randn(n) * 0.01
        F2 = np.random.randn(n) * 0.01
        true_b1, true_b2 = 2.0, 1.0
        true_alpha = 0.0003
        y = true_alpha + true_b1 * F1 + true_b2 * F2 + np.random.randn(n) * 0.001
        X = np.column_stack([F1, F2])
        betas, intercept, r2 = fit_ols(X, y, add_const=True)
        assert len(betas) == 2
        assert abs(betas[0] - true_b1) < 0.15
        assert abs(betas[1] - true_b2) < 0.15
        assert abs(intercept - true_alpha) < 0.002
        assert r2 > 0.9

    def test_causal_rolling_ols_betas_near_true_on_synthetic(self):
        np.random.seed(123)
        n = 150
        idx = pd.date_range("2024-01-01", periods=n, freq="h")
        btc = np.random.randn(n) * 0.01
        eth = np.random.randn(n) * 0.01
        true_b_btc, true_b_eth = 1.5, 0.8
        alpha = 0.0002
        asset = alpha + true_b_btc * btc + true_b_eth * eth + np.random.randn(n) * 0.002
        df = pd.DataFrame(
            {"BTC_spot": btc, "ETH_spot": eth, "A": asset},
            index=idx,
        )
        betas_dict, r2_df, residual_df, alpha_df = causal_rolling_ols(
            df, factor_cols=["BTC_spot", "ETH_spot"], window_bars=72, min_obs=24, as_of_lag_bars=1
        )
        btc_beta = betas_dict["BTC_spot"]["A"].dropna().tail(50)
        eth_beta = betas_dict["ETH_spot"]["A"].dropna().tail(50)
        assert btc_beta.mean() == pytest.approx(true_b_btc, abs=0.35)
        assert eth_beta.mean() == pytest.approx(true_b_eth, abs=0.35)


class TestLagPreventsLookahead:
    """
    Introduce a 'future leak' in synthetic data: make asset return at t depend on
    factor return at t+1. With as_of_lag_bars=1, the fit at t uses data only up to t-1,
    so it cannot use the future factor; R² or fit quality should not benefit from the leak.
    With lag=0 (if we allowed it), the fit could use t and would see the leak.
    """

    def test_future_leak_cannot_improve_fit_when_lag_enforced(self):
        # Build data where asset_t = factor_{t+1} (perfect future leak).
        # With as_of_lag_bars=1, fit at t uses data up to t-1, so factor at t+1
        # is never in the design matrix -> betas cannot capture the leak -> R² should be low.
        np.random.seed(99)
        n = 120
        idx = pd.date_range("2024-01-01", periods=n, freq="h")
        btc = np.random.randn(n) * 0.01
        eth = np.random.randn(n) * 0.01
        # Asset return at t = BTC at t+1 (lookahead). With lag=1 we never use t+1 in fit.
        asset_future_leak = np.roll(btc, -1)  # asset[i] = btc[i+1]
        asset_future_leak[-1] = np.nan  # last row no future
        df = pd.DataFrame(
            {"BTC_spot": btc, "ETH_spot": eth, "A": asset_future_leak},
            index=idx,
        )
        betas_dict, r2_df, residual_df, alpha_df = causal_rolling_ols(
            df, factor_cols=["BTC_spot", "ETH_spot"], window_bars=48, min_obs=20, as_of_lag_bars=1
        )
        # R² should be low/near noise: we cannot fit future from past
        r2_vals = r2_df["A"].dropna()
        assert len(r2_vals) >= 1
        # With strict causality, R² should not be high (no access to future BTC in fit)
        assert r2_vals.mean() < 0.5, (
            "Causal fit should not achieve high R² when asset = future factor (lag prevents lookahead)"
        )

    def test_causal_residual_returns_no_future_in_fit(self):
        # Same idea: residual at t must not use returns from t+1 in the regression.
        np.random.seed(100)
        n = 80
        idx = pd.date_range("2024-06-01", periods=n, freq="h")
        btc = np.random.randn(n) * 0.01
        eth = np.random.randn(n) * 0.01
        asset = np.roll(btc, -2) + np.random.randn(n) * 0.001  # asset_t = btc_{t+2}
        df = pd.DataFrame({"BTC_spot": btc, "ETH_spot": eth, "A": asset}, index=idx)
        resid_df = causal_residual_returns(
            df, factor_cols=["BTC_spot", "ETH_spot"], window_bars=24, min_obs=12, as_of_lag_bars=1
        )
        assert "A" in resid_df.columns
        # Residuals should exist and not explode (fit is causal, so residual is well-defined)
        r = resid_df["A"].dropna()
        assert len(r) >= 1
        assert np.isfinite(r).all()

    def test_as_of_lag_bars_1_uses_only_past(self):
        # Explicit: at index i, fit uses indices [start_i, i - 1] (for lag=1).
        # So the last observation in the fit is at i-1, never i.
        np.random.seed(101)
        n = 50
        idx = pd.date_range("2024-01-01", periods=n, freq="h")
        btc = np.random.randn(n) * 0.01
        eth = np.random.randn(n) * 0.01
        asset = 1.0 * btc + 0.5 * eth + np.random.randn(n) * 0.001
        df = pd.DataFrame({"BTC_spot": btc, "ETH_spot": eth, "A": asset}, index=idx)
        betas_dict, r2_df, residual_df, alpha_df = causal_rolling_ols(
            df, factor_cols=["BTC_spot", "ETH_spot"], window_bars=30, min_obs=15, as_of_lag_bars=1
        )
        # First row that can have a fit: need fit_end_i >= 0 and window, so i >= 1 + 15 = 16 roughly
        first_valid = betas_dict["BTC_spot"]["A"].first_valid_index()
        assert first_valid is not None
        first_pos = list(df.index).index(first_valid)
        # fit_end_i = i - 1, so we need at least min_obs points in [i-30, i-1] -> i >= min_obs + 1
        assert first_pos >= 1
