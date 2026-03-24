"""
D6 / Slice 8: multifactor OLS for strict walk-forward must not use same-fold test
rows in the regression window when summarizing mf_metrics at test timestamps.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_analyzer.factors import (
    aggregate_multifactor_metrics_walk_forward,
    build_factor_matrix,
    rolling_multifactor_ols,
)
from crypto_analyzer.fold_causality.folds import FoldSpec


def test_aggregate_mf_ignores_test_period_in_fit_window():
    """
    Train: asset return ~ noise (factor betas ~ 0). Test: asset tracks BTC strongly.
    Full-series rolling OLS at late test bars uses prior test rows in the window → inflated BTC beta.
    Walk-forward aggregate uses only train timestamps in the fit → beta stays near 0.
    """
    np.random.seed(7)
    n = 400
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    btc = np.random.randn(n) * 0.02
    eth = np.random.randn(n) * 0.02
    noise = np.random.randn(n) * 0.01
    y = np.zeros(n)
    # Train: orthogonal to factors
    y[:] = noise.copy()
    # Test: load on BTC only
    test_start_i = 240
    y[test_start_i:] = 3.0 * btc[test_start_i:] + np.random.randn(n - test_start_i) * 0.002

    returns_df = pd.DataFrame(
        {"BTC_spot": btc, "ETH_spot": eth, "asset_A": y},
        index=idx,
    )
    factor_df = build_factor_matrix(returns_df)
    fold = FoldSpec(
        fold_id="fold_0",
        train_start_ts=idx[0],
        train_end_ts=idx[test_start_i - 1],
        test_start_ts=idx[test_start_i],
        test_end_ts=idx[320],
        purge_gap_bars=0,
        embargo_bars=0,
        asof_lag_bars=0,
    )

    wf_agg = aggregate_multifactor_metrics_walk_forward(returns_df, factor_df, [fold], window=72, min_obs=24)
    assert "beta_btc_mean" in wf_agg
    assert wf_agg["beta_btc_mean"] < 0.8, (
        f"Train-only fit should not pick up test-period BTC loading; got {wf_agg['beta_btc_mean']}"
    )

    betas_dict, _, _ = rolling_multifactor_ols(returns_df, factor_df, window=72, min_obs=24)
    test_betas = betas_dict["BTC_spot"]["asset_A"].loc[idx[test_start_i] : idx[320]].dropna()
    assert len(test_betas) > 20
    full_mean_test = float(test_betas.mean())
    assert full_mean_test > 1.2, (
        f"Full-series rolling OLS on test window should reflect strong factor load; got {full_mean_test}"
    )
    assert wf_agg["beta_btc_mean"] < full_mean_test * 0.45, (
        "Walk-forward aggregate must be far below full-series test-window mean when test leaks into window"
    )


def test_aggregate_mf_empty_folds_returns_empty():
    returns_df = pd.DataFrame(
        {"BTC_spot": [0.01, -0.01], "ETH_spot": [0.0, 0.0], "a": [0.0, 0.0]},
        index=pd.date_range("2024-01-01", periods=2, freq="h"),
    )
    fm = build_factor_matrix(returns_df)
    assert aggregate_multifactor_metrics_walk_forward(returns_df, fm, []) == {}
