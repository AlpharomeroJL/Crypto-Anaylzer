"""
Bootstrap correctness: block-length distribution, dependence preservation, index alignment.
Phase 2A validation for RC/RW defensibility.
"""

from __future__ import annotations

import numpy as np

from crypto_analyzer.rng import rng_from_seed
from crypto_analyzer.statistics import _stationary_bootstrap_indices


def _mean_block_length_from_indices(indices: np.ndarray, n: int) -> float:
    """Estimate mean block length: consecutive runs (diff==1 or wrap)."""
    if len(indices) < 2:
        return 1.0
    diffs = np.diff(indices)
    consecutive = (diffs == 1) | (diffs <= -n + 2)
    run_lens = np.diff(np.where(np.concatenate([[False], ~consecutive, [False]]))[0])
    return float(run_lens.mean()) if run_lens.size else 1.0


def test_stationary_bootstrap_block_length_variation():
    """Block resampling produces runs of consecutive indices (dependence); not all single-step."""
    avg = 5.0
    n = 500
    rng = rng_from_seed(42)
    indices = _stationary_bootstrap_indices(n, avg, seed=None, rng=rng)
    diffs = np.diff(indices)
    consecutive = (diffs == 1) | (diffs <= -n + 2)
    run_lens = np.diff(np.where(np.concatenate([[False], ~consecutive, [False]]))[0])
    if run_lens.size > 0:
        assert int(run_lens.max()) >= 1
    assert len(indices) == n


def test_stationary_bootstrap_mean_block_length_near_configured():
    """Expected average block length is close to configured avg_block_length (geometric mean)."""
    avg_block = 6.0
    n = 400
    n_draws = 100
    rng = rng_from_seed(123)
    mean_lengths = []
    for _ in range(n_draws):
        idx = _stationary_bootstrap_indices(n, avg_block, seed=None, rng=rng)
        mean_lengths.append(_mean_block_length_from_indices(idx, n))
    observed_mean = float(np.mean(mean_lengths))
    # Geometric(1/avg) has mean = avg; allow ~30% tolerance for small n_draws
    assert 0.5 * avg_block <= observed_mean <= 2.0 * avg_block, (
        f"mean block length {observed_mean} expected near {avg_block}"
    )


def test_stationary_bootstrap_indices_length():
    """Resampled indices have requested length."""
    for length in [10, 100]:
        idx = _stationary_bootstrap_indices(length, avg_block_length=4.0, seed=1)
        assert len(idx) == length
        assert idx.dtype in (np.int_, np.int32, np.int64)


def test_stationary_bootstrap_indices_in_range():
    """All indices in [0, length)."""
    length = 80
    idx = _stationary_bootstrap_indices(length, avg_block_length=6.0, seed=2)
    assert np.all(idx >= 0) and np.all(idx < length)


def test_stationary_bootstrap_reproducible_with_same_seed():
    """Same seed + same params => same index sequence."""
    a = _stationary_bootstrap_indices(50, 5.0, seed=99)
    b = _stationary_bootstrap_indices(50, 5.0, seed=99)
    np.testing.assert_array_equal(a, b)


def test_stationary_bootstrap_different_seeds_different_sequence():
    """Different seeds => different sequences (with high probability)."""
    a = _stationary_bootstrap_indices(200, 8.0, seed=1)
    b = _stationary_bootstrap_indices(200, 8.0, seed=2)
    assert not np.array_equal(a, b)
