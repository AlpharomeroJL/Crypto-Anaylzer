"""Statistics: block bootstrap outputs."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.statistics import block_bootstrap_pnl, safe_nanmean, sharpe_ci, significance_summary


def test_block_bootstrap_outputs():
    """Bootstrap CI returns lo <= mid <= hi and correct length."""
    np.random.seed(47)
    n = 100
    pnl = pd.Series(np.random.randn(n) * 0.01)
    lo, mid, hi = sharpe_ci(pnl, "1h", block_size=10, n=200, seed=42)
    assert lo <= mid <= hi or (np.isnan(lo) and np.isnan(mid) and np.isnan(hi))
    dist = block_bootstrap_pnl(pnl, block_size=10, n=100, seed=42)
    assert len(dist) == 100
    summ = significance_summary(pnl, "1h", block_size=10, n_bootstrap=50)
    assert "sharpe_annual" in summ
    assert "sharpe_ci_95_lo" in summ and "sharpe_ci_95_hi" in summ
    assert summ["sharpe_ci_95_lo"] <= summ["sharpe_ci_95_hi"] or (
        np.isnan(summ["sharpe_ci_95_lo"]) and np.isnan(summ["sharpe_ci_95_hi"])
    )


def test_stationary_bootstrap_reproducible():
    """Fixed seed -> identical bootstrap samples for stationary method."""
    np.random.seed(11)
    pnl = pd.Series(np.random.randn(80) * 0.01)
    dist1 = block_bootstrap_pnl(pnl, block_size=10, n=50, seed=42, method="stationary", avg_block_length=10.0)
    dist2 = block_bootstrap_pnl(pnl, block_size=10, n=50, seed=42, method="stationary", avg_block_length=10.0)
    assert len(dist1) == 50 and len(dist2) == 50
    np.testing.assert_array_almost_equal(dist1, dist2)


def test_stationary_bootstrap_marginal_smoke():
    """Stationary bootstrap resamples: mean of resampled series approximates original mean."""
    np.random.seed(13)
    pnl = pd.Series(np.random.randn(200) * 0.01)
    dist = block_bootstrap_pnl(pnl, block_size=20, n=200, seed=7, method="stationary", avg_block_length=15.0)
    assert len(dist) == 200
    # Total return distribution should be centered roughly near 0 (small sample variability)
    assert np.abs(np.mean(dist)) < 0.5


def test_sharpe_ci_deterministic_with_seed():
    """Same seed -> same CI bounds for both methods."""
    np.random.seed(17)
    pnl = pd.Series(np.random.randn(100) * 0.01)
    lo1, m1, hi1 = sharpe_ci(pnl, "1h", block_size=10, n=100, seed=99, method="block_fixed")
    lo2, m2, hi2 = sharpe_ci(pnl, "1h", block_size=10, n=100, seed=99, method="block_fixed")
    assert lo1 == lo2 and hi1 == hi2
    lo3, m3, hi3 = sharpe_ci(pnl, "1h", block_size=10, n=100, seed=99, method="stationary", avg_block_length=10.0)
    lo4, m4, hi4 = sharpe_ci(pnl, "1h", block_size=10, n=100, seed=99, method="stationary", avg_block_length=10.0)
    assert lo3 == lo4 and hi3 == hi4


def test_significance_summary_includes_bootstrap_metadata():
    """significance_summary returns bootstrap_method, bootstrap_seed, block_length."""
    np.random.seed(19)
    pnl = pd.Series(np.random.randn(60) * 0.01)
    summ = significance_summary(
        pnl, "1h", block_size=10, n_bootstrap=30, seed=1, method="stationary", avg_block_length=10.0
    )
    assert summ.get("bootstrap_method") == "stationary"
    assert summ.get("bootstrap_seed") == 1
    assert summ.get("block_length") == 10.0


def test_safe_nanmean_no_warning():
    """safe_nanmean returns None for empty/all-NaN without RuntimeWarning."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        assert safe_nanmean([]) is None
        assert safe_nanmean([float("nan"), float("nan")]) is None
        assert safe_nanmean(None) is None

    result = safe_nanmean([1.0, 2.0, float("nan")])
    assert result is not None
    assert abs(result - 1.5) < 1e-9

    assert safe_nanmean([0.0]) == 0.0
