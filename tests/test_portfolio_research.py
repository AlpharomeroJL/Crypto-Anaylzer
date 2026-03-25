"""Portfolio: vol target scaling, beta neutralization."""

import numpy as np
import pandas as pd

from crypto_analyzer.portfolio import (
    adaptive_long_short_k,
    beta_neutralize_weights,
    ema_smooth_weights,
    long_short_from_ranks,
    vol_target_weights,
)


def test_vol_target_scaling():
    """Weights reduce effective risk as volatility increases (inverse vol)."""
    np.random.seed(45)
    n = 50
    # Low vol asset, high vol asset
    low_vol = np.random.randn(n) * 0.005
    high_vol = np.random.randn(n) * 0.02
    returns_window = pd.DataFrame({"a": low_vol, "b": high_vol})
    w = vol_target_weights(returns_window, target_annual_vol=0.15, freq="1h")
    assert w["a"] > w["b"], "Lower vol asset should get higher weight (inverse vol)"


def test_beta_neutralization():
    """Portfolio beta close to 0 after neutralization."""
    np.random.seed(46)
    weights = pd.Series({"x": 0.5, "y": 0.5})
    betas = pd.Series({"x": 1.2, "y": 0.8})
    w_adj = beta_neutralize_weights(weights, betas, target_beta=0.0)
    port_beta = (w_adj * betas).sum()
    assert abs(port_beta) < 0.01, "Portfolio beta should be ~0 after neutralization"


def test_adaptive_long_short_k_nine_names():
    """9-name panel: cap each leg at 2 (n//4), not default 3."""
    tk, bk = adaptive_long_short_k(9, 3, 3)
    assert tk == 2 and bk == 2


def test_long_short_signal_abs_weights():
    """Long leg weights sum to +0.5; short to -0.5 by |signal|."""
    idx = pd.date_range("2024-01-01", periods=1, freq="h", tz="UTC")
    ranks = pd.DataFrame([[0.9, 0.5, 0.1]], index=idx, columns=["a", "b", "c"])
    sig = pd.DataFrame([[2.0, 1.0, -1.0]], index=idx, columns=["a", "b", "c"])
    w = long_short_from_ranks(ranks, 1, 1, gross_leverage=1.0, signal_df=sig, within_bucket="signal_abs")
    assert w.loc[idx[0], "a"] > 0 and w.loc[idx[0], "c"] < 0
    assert abs(w.loc[idx[0]].sum()) < 1e-9


def test_ema_smooth_weights_reduces_jump():
    w1 = pd.DataFrame([[1.0, 0.0], [0.0, 1.0]], columns=["a", "b"])
    sm = ema_smooth_weights(w1, 0.5)
    assert sm.iloc[1, 0] == 0.5 and sm.iloc[1, 1] == 0.5
