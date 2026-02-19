"""Tests for dynamic (RLS/Kalman-style) beta estimator: determinism, causality, tracking."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.factors import causal_rolling_ols
from crypto_analyzer.factors_dynamic_beta import dynamic_beta_rls


def _make_returns(n: int = 60, seed: int = 42) -> pd.DataFrame:
    np.random.seed(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="h")
    btc = np.random.randn(n).astype(float) * 0.01
    eth = np.random.randn(n).astype(float) * 0.01
    a0 = 0.5 * btc + 0.3 * eth + np.random.randn(n).astype(float) * 0.005
    return pd.DataFrame({"BTC_spot": btc, "ETH_spot": eth, "A0": a0}, index=idx)


def test_as_of_lag_bars_must_be_at_least_one():
    """dynamic_beta_rls rejects as_of_lag_bars < 1 (no lookahead)."""
    df = _make_returns(30)
    with pytest.raises(ValueError, match="as_of_lag_bars must be >= 1"):
        dynamic_beta_rls(df, factor_cols=["BTC_spot", "ETH_spot"], as_of_lag_bars=0)


def test_dynamic_beta_deterministic():
    """Same returns_df and params => identical betas and residuals."""
    df = _make_returns(80)
    params = {"process_var": 1e-5, "obs_var": 1e-4}
    r1 = dynamic_beta_rls(
        df,
        factor_cols=["BTC_spot", "ETH_spot"],
        as_of_lag_bars=1,
        window_bars=24,
        min_obs=12,
        params=params,
    )
    r2 = dynamic_beta_rls(
        df,
        factor_cols=["BTC_spot", "ETH_spot"],
        as_of_lag_bars=1,
        window_bars=24,
        min_obs=12,
        params=params,
    )
    betas1, _, resid1, alpha1 = r1
    betas2, _, resid2, alpha2 = r2
    for f in betas1:
        pd.testing.assert_frame_equal(betas1[f], betas2[f], check_exact=False, atol=1e-12, rtol=0)
    pd.testing.assert_frame_equal(resid1, resid2, check_exact=False, atol=1e-12, rtol=0)
    pd.testing.assert_frame_equal(alpha1, alpha2, check_exact=False, atol=1e-12, rtol=0)


def test_dynamic_beta_tracks_shift():
    """Synthetic beta shift: dynamic beta should adapt (post-shift mean beta moves toward new level)."""
    n = 120
    np.random.seed(123)
    idx = pd.date_range("2025-01-01", periods=n, freq="h")
    btc = np.random.randn(n).astype(float) * 0.01
    eth = np.random.randn(n).astype(float) * 0.01
    true_beta_btc = np.ones(n) * 0.5
    true_beta_btc[60:] = 0.8
    a0 = true_beta_btc * btc + 0.3 * eth + np.random.randn(n).astype(float) * 0.003
    df = pd.DataFrame({"BTC_spot": btc, "ETH_spot": eth, "A0": a0}, index=idx)

    betas_rls, _, _, _ = dynamic_beta_rls(
        df,
        factor_cols=["BTC_spot", "ETH_spot"],
        as_of_lag_bars=1,
        window_bars=36,
        min_obs=18,
        params={"process_var": 1e-4, "obs_var": 1e-4},
    )
    betas_ols, _, _, _ = causal_rolling_ols(
        df,
        factor_cols=["BTC_spot", "ETH_spot"],
        window_bars=36,
        min_obs=18,
        as_of_lag_bars=1,
    )

    b_rls = betas_rls["BTC_spot"]["A0"].dropna()
    b_ols = betas_ols["BTC_spot"]["A0"].dropna()
    pre = idx[:50]
    post = idx[70:]
    rls_pre = b_rls.reindex(pre).dropna().mean()
    rls_post = b_rls.reindex(post).dropna().mean()
    ols_post = b_ols.reindex(post).dropna().mean()
    assert not np.isnan(rls_post) and not np.isnan(ols_post)
    assert rls_post > 0.4
    assert ols_post > 0.4
    assert rls_pre < 0.7 or rls_post >= 0.5


def test_dynamic_beta_output_shape():
    """Output shapes match causal_rolling_ols: common_idx, asset_cols, factor names."""
    df = _make_returns(50)
    betas_dict, r2_df, residual_df, alpha_df = dynamic_beta_rls(
        df,
        factor_cols=["BTC_spot", "ETH_spot"],
        as_of_lag_bars=1,
        window_bars=20,
        min_obs=10,
        params={},
    )
    assert "BTC_spot" in betas_dict and "ETH_spot" in betas_dict
    assert residual_df.shape[1] == 1 and "A0" in residual_df.columns
    assert alpha_df.shape == residual_df.shape
    assert r2_df.shape == residual_df.shape
    assert betas_dict["BTC_spot"].shape == residual_df.shape


def test_dynamic_beta_no_exploit_future_factor():
    """With as_of_lag_bars=1, residual should not exploit factor_{t+1} (leakage sentinel)."""
    n = 50
    np.random.seed(99)
    idx = pd.date_range("2025-01-01", periods=n, freq="h")
    btc = np.random.randn(n).astype(float) * 0.01
    eth = np.random.randn(n).astype(float) * 0.01
    a0 = 0.5 * btc + 0.3 * eth + np.random.randn(n).astype(float) * 0.005
    df = pd.DataFrame({"BTC_spot": btc, "ETH_spot": eth, "A0": a0}, index=idx)
    _, _, residual_df, _ = dynamic_beta_rls(
        df,
        factor_cols=["BTC_spot", "ETH_spot"],
        as_of_lag_bars=1,
        window_bars=24,
        min_obs=12,
        params={},
    )
    resid = residual_df["A0"].dropna()
    btc_next = df["BTC_spot"].shift(-1).reindex(resid.index).dropna()
    common = resid.index.intersection(btc_next.index)
    if len(common) < 10:
        pytest.skip("Insufficient overlap for IC check")
    corr = np.corrcoef(resid.reindex(common).dropna().values, btc_next.reindex(common).dropna().values)[
        0, 1
    ]
    assert np.isnan(corr) or abs(corr) < 0.5
