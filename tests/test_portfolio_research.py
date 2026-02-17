"""Portfolio: vol target scaling, beta neutralization."""
import numpy as np
import pandas as pd
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.portfolio import (
    vol_target_weights,
    beta_neutralize_weights,
    long_short_from_ranks,
    portfolio_returns_from_weights,
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
