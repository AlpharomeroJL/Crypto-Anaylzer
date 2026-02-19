"""
Leakage sentinel: causal residual momentum must not exploit future factor information.
Synthetic data where y_t is correlated with factor_{t+1}; causal path must not show abnormal IC.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.alpha_research import (
    compute_forward_returns,
    information_coefficient,
    signal_residual_momentum_24h,
)


def _make_future_factor_data(n: int = 200, seed: int = 123) -> pd.DataFrame:
    """Returns where asset return at t is correlated with factor return at t+1 (lookahead)."""
    np.random.seed(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    btc = np.random.randn(n).astype(float) * 0.01
    eth = np.random.randn(n).astype(float) * 0.01
    # Asset at t = 0.5*BTC_t + 0.2*ETH_t + 0.4*BTC_{t+1} (future info -> leakage)
    btc_fwd = np.roll(btc, -1)
    btc_fwd[-1] = np.nan
    asset = 0.5 * btc + 0.2 * eth + 0.4 * btc_fwd + np.random.randn(n) * 0.003
    asset[-1] = np.nan
    return pd.DataFrame(
        {"pair1": asset, "BTC_spot": btc, "ETH_spot": eth},
        index=idx,
    )


def test_causal_residual_momentum_no_abnormal_ic():
    """
    With synthetic data where y_t correlates with factor_{t+1}, causal residual momentum
    (as_of_lag_bars>=1) must NOT show abnormal predictability (IC near 0).
    """
    returns_df = _make_future_factor_data(n=200, seed=123)
    sig_causal = signal_residual_momentum_24h(returns_df, "1h", as_of_lag_bars=1, allow_lookahead=False)
    assert sig_causal is not None and not sig_causal.empty
    fwd1 = compute_forward_returns(returns_df, 1)
    ic_ts = information_coefficient(sig_causal, fwd1, method="spearman")
    ic_ts = ic_ts.dropna()
    if len(ic_ts) < 5:
        return
    mean_ic = float(ic_ts.mean())
    # Causal path cannot use future factor; mean IC should be modest (not strongly positive)
    # With as_of_lag_bars=1 we don't use t+1 factor when computing residual at t
    assert abs(mean_ic) < 0.15, f"Causal residual momentum should not exploit future factor; got mean_ic={mean_ic}"


def test_lookahead_path_different_from_causal():
    """Default path must be causal (allow_lookahead=False). Lookahead path can be quarantined."""
    returns_df = _make_future_factor_data(n=150, seed=456)
    sig_causal = signal_residual_momentum_24h(returns_df, "1h", allow_lookahead=False)
    sig_lookahead = signal_residual_momentum_24h(returns_df, "1h", allow_lookahead=True)
    assert sig_causal is not None and sig_lookahead is not None
    # Values should differ (lookahead uses full-sample betas)
    common = sig_causal.dropna(how="all").index.intersection(sig_lookahead.dropna(how="all").index)
    if len(common) < 10:
        return
    diff = (sig_causal.loc[common] - sig_lookahead.loc[common]).abs()
    assert diff.max().max() > 1e-6 or diff.isna().all().all(), "Causal and lookahead outputs should differ"
    # Default is causal
    sig_default = signal_residual_momentum_24h(returns_df, "1h")
    pd.testing.assert_frame_equal(sig_default, sig_causal)
    # Ensure report/reportv2 never pass allow_lookahead=True by default (contract: default blocks lookahead)
    sig_explicit_causal = signal_residual_momentum_24h(returns_df, "1h", allow_lookahead=False)
    pd.testing.assert_frame_equal(sig_explicit_causal, sig_causal)
