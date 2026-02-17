"""Residuals reduce correlation with factors on synthetic data."""
import numpy as np
import pandas as pd
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.factors import (
    compute_ols_betas,
    compute_residual_returns,
)


def test_residuals_orthogonal_to_factors():
    """On synthetic data, residual should have lower correlation with factors than raw."""
    np.random.seed(42)
    n = 200
    btc = np.random.randn(n) * 0.01
    eth = np.random.randn(n) * 0.01
    # Asset = 0.5*BTC + 0.3*ETH + noise
    noise = np.random.randn(n) * 0.005
    asset = 0.5 * btc + 0.3 * eth + noise
    y = pd.Series(asset)
    X = pd.DataFrame({"BTC_spot": btc, "ETH_spot": eth})
    betas, alpha = compute_ols_betas(y, X)
    assert len(betas) == 2
    resid = compute_residual_returns(y, X, betas, alpha)
    assert len(resid) > 0
    btc_aligned = X.loc[resid.index, "BTC_spot"].values
    corr_resid_btc = np.corrcoef(resid.values, btc_aligned)[0, 1]
    # OLS residual should be uncorrelated with factors in sample (orthogonality)
    assert abs(corr_resid_btc) < 0.1
