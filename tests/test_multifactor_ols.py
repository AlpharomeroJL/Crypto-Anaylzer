"""
Tests for multi-factor OLS: fit_ols and rolling_multifactor_ols.
Synthetic data where y = 2*BTC + 1*ETH + noise; ensure estimated betas near
2 and 1, residual mean ~0, R^2 high.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.factors import fit_ols, rolling_multifactor_ols


class TestFitOls:
    def test_basic_recovery(self):
        np.random.seed(0)
        n = 500
        x1 = np.random.randn(n) * 0.01
        x2 = np.random.randn(n) * 0.01
        noise = np.random.randn(n) * 0.001
        y = 2.0 * x1 + 1.0 * x2 + 0.0005 + noise

        X = np.column_stack([x1, x2])
        betas, intercept, r2 = fit_ols(X, y, add_const=True)

        assert len(betas) == 2
        assert abs(betas[0] - 2.0) < 0.15, f"beta_btc={betas[0]}"
        assert abs(betas[1] - 1.0) < 0.15, f"beta_eth={betas[1]}"
        assert r2 > 0.9
        assert abs(intercept - 0.0005) < 0.002

    def test_degenerate_input(self):
        betas, intercept, r2 = fit_ols(np.array([]).reshape(0, 1), np.array([]))
        assert np.isnan(intercept)
        assert np.isnan(r2)

    def test_no_constant(self):
        np.random.seed(1)
        n = 300
        x = np.random.randn(n) * 0.01
        y = 3.0 * x + np.random.randn(n) * 0.001
        betas, intercept, r2 = fit_ols(x.reshape(-1, 1), y, add_const=False)
        assert abs(betas[0] - 3.0) < 0.2
        assert intercept == 0.0
        assert r2 > 0.9


class TestRollingMultifactorOls:
    @pytest.fixture
    def synthetic_data(self):
        np.random.seed(42)
        n = 200
        idx = pd.date_range("2024-01-01", periods=n, freq="h")
        btc = pd.Series(np.random.randn(n) * 0.01, index=idx, name="BTC_spot")
        eth = pd.Series(np.random.randn(n) * 0.01, index=idx, name="ETH_spot")
        noise = np.random.randn(n) * 0.002
        asset = 2.0 * btc.values + 1.0 * eth.values + noise

        returns_df = pd.DataFrame(
            {
                "BTC_spot": btc.values,
                "ETH_spot": eth.values,
                "asset_A": asset,
            },
            index=idx,
        )
        factor_df = returns_df[["BTC_spot", "ETH_spot"]]
        return returns_df, factor_df

    def test_betas_near_true_values(self, synthetic_data):
        returns_df, factor_df = synthetic_data
        betas_dict, r2_df, residual_df = rolling_multifactor_ols(returns_df, factor_df, window=72, min_obs=24)

        assert "BTC_spot" in betas_dict
        assert "ETH_spot" in betas_dict
        assert "asset_A" in betas_dict["BTC_spot"].columns

        btc_beta_tail = betas_dict["BTC_spot"]["asset_A"].dropna().tail(50)
        eth_beta_tail = betas_dict["ETH_spot"]["asset_A"].dropna().tail(50)

        assert abs(btc_beta_tail.mean() - 2.0) < 0.3, f"mean btc beta = {btc_beta_tail.mean()}"
        assert abs(eth_beta_tail.mean() - 1.0) < 0.3, f"mean eth beta = {eth_beta_tail.mean()}"

    def test_r2_high(self, synthetic_data):
        returns_df, factor_df = synthetic_data
        _, r2_df, _ = rolling_multifactor_ols(returns_df, factor_df, window=72, min_obs=24)
        r2_tail = r2_df["asset_A"].dropna().tail(50)
        assert r2_tail.mean() > 0.85

    def test_residual_mean_near_zero(self, synthetic_data):
        returns_df, factor_df = synthetic_data
        _, _, residual_df = rolling_multifactor_ols(returns_df, factor_df, window=72, min_obs=24)
        resid = residual_df["asset_A"].dropna()
        assert len(resid) > 50
        assert abs(resid.mean()) < 0.005

    def test_graceful_degradation_missing_eth(self):
        """When ETH_spot is missing, fall back to BTC-only."""
        np.random.seed(99)
        n = 150
        idx = pd.date_range("2024-06-01", periods=n, freq="h")
        btc = np.random.randn(n) * 0.01
        asset = 1.5 * btc + np.random.randn(n) * 0.002
        returns_df = pd.DataFrame({"BTC_spot": btc, "asset_X": asset}, index=idx)
        factor_df = returns_df[["BTC_spot"]]

        betas_dict, r2_df, residual_df = rolling_multifactor_ols(returns_df, factor_df, window=48, min_obs=20)
        assert "BTC_spot" in betas_dict
        assert "ETH_spot" not in betas_dict
        btc_beta = betas_dict["BTC_spot"]["asset_X"].dropna().tail(30)
        assert abs(btc_beta.mean() - 1.5) < 0.3

    def test_no_factors_returns_empty(self):
        n = 50
        idx = pd.date_range("2024-01-01", periods=n, freq="h")
        returns_df = pd.DataFrame({"asset_A": np.random.randn(n)}, index=idx)
        factor_df = pd.DataFrame(index=idx)
        betas_dict, r2_df, residual_df = rolling_multifactor_ols(returns_df, factor_df)
        assert len(betas_dict) == 0
        assert r2_df.empty or r2_df.isna().all().all()

    def test_alignment_no_forward_looking(self, synthetic_data):
        """Verify that betas at time t only use data up to time t."""
        returns_df, factor_df = synthetic_data
        betas_dict, _, _ = rolling_multifactor_ols(returns_df, factor_df, window=72, min_obs=24)
        btc_betas = betas_dict["BTC_spot"]["asset_A"]
        first_valid = btc_betas.first_valid_index()
        idx_list = list(returns_df.index)
        first_pos = idx_list.index(first_valid)
        assert first_pos >= 23, "Betas should not appear before min_obs rows"
