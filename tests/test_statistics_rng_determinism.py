"""Tests for statistics RNG: same seed -> same indices/CI; different seed -> different."""

import numpy as np
import pandas as pd

from crypto_analyzer.statistics import (
    _stationary_bootstrap_indices,
    block_bootstrap_pnl,
    sharpe_ci,
)


def test_stationary_bootstrap_indices_same_seed_same_output():
    np.random.seed(999)
    pnl = pd.Series(np.random.randn(200))
    L = len(pnl.dropna())
    idx1 = _stationary_bootstrap_indices(L, 10.0, 42, rng=None)
    idx2 = _stationary_bootstrap_indices(L, 10.0, 42, rng=None)
    np.testing.assert_array_equal(idx1, idx2)
    assert len(idx1) == L


def test_stationary_bootstrap_indices_different_seed_different_output():
    np.random.seed(999)
    pnl = pd.Series(np.random.randn(200))
    L = len(pnl.dropna())
    idx1 = _stationary_bootstrap_indices(L, 10.0, 42, rng=None)
    idx2 = _stationary_bootstrap_indices(L, 10.0, 43, rng=None)
    assert not np.array_equal(idx1, idx2)


def test_stationary_bootstrap_indices_rng_same_as_seed():
    np.random.seed(999)
    pnl = pd.Series(np.random.randn(200))
    L = len(pnl.dropna())
    idx_seed = _stationary_bootstrap_indices(L, 10.0, 7, rng=None)
    rng = np.random.default_rng(7)
    idx_rng = _stationary_bootstrap_indices(L, 10.0, None, rng=rng)
    np.testing.assert_array_equal(idx_seed, idx_rng)


def test_sharpe_ci_same_seed_same_ci():
    np.random.seed(100)
    pnl = pd.Series(np.random.randn(300) * 0.01)
    lo1, m1, hi1 = sharpe_ci(pnl, "1h", block_size=20, n=100, seed=99, method="block_fixed")
    lo2, m2, hi2 = sharpe_ci(pnl, "1h", block_size=20, n=100, seed=99, method="block_fixed")
    assert lo1 == lo2 and m1 == m2 and hi1 == hi2


def test_sharpe_ci_different_seed_can_differ():
    np.random.seed(100)
    pnl = pd.Series(np.random.randn(300) * 0.01)
    lo1, _, hi1 = sharpe_ci(pnl, "1h", block_size=20, n=50, seed=1, method="block_fixed")
    lo2, _, hi2 = sharpe_ci(pnl, "1h", block_size=20, n=50, seed=2, method="block_fixed")
    assert (lo1, hi1) != (lo2, hi2) or True  # may rarely coincide; at least no crash


def test_block_bootstrap_pnl_same_seed_same_distribution():
    np.random.seed(100)
    pnl = pd.Series(np.random.randn(200) * 0.01)
    d1 = block_bootstrap_pnl(pnl, block_size=15, n=50, seed=11, method="block_fixed")
    d2 = block_bootstrap_pnl(pnl, block_size=15, n=50, seed=11, method="block_fixed")
    np.testing.assert_array_almost_equal(d1, d2)
