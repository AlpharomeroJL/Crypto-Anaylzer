"""Tests for null suite: outputs generated, false positive rate under null."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from crypto_analyzer.null_suite import (
    null_1_random_ranks,
    null_2_permute_signal,
    null_3_block_shuffle,
    run_null_suite,
    write_null_suite_artifacts,
)


def _fixture(n_ts: int = 40, n_assets: int = 10, seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n_ts, freq="h")
    cols = [f"A{i}" for i in range(n_assets)]
    signal_df = pd.DataFrame(rng.standard_normal((n_ts, n_assets)), index=idx, columns=cols)
    returns_df = pd.DataFrame(rng.standard_normal((n_ts, n_assets)) * 0.01, index=idx, columns=cols)
    return signal_df, returns_df


def test_null_suite_produces_artifacts():
    """Null suite writes null_ic_dist.csv, null_sharpe_dist.csv, null_pvalues.json."""
    signal_df, returns_df = _fixture(30, 8)
    result = run_null_suite(signal_df, returns_df, n_sim=20, block_size=5, seed=42)
    assert hasattr(result, "null_ic_means")
    assert "null1" in result.null_ic_means
    assert len(result.null_ic_means["null1"]) == 20
    with tempfile.TemporaryDirectory() as d:
        paths = write_null_suite_artifacts(result, d)
        assert len(paths) >= 2
        assert any("null_ic_dist" in p for p in paths)
        assert any("null_sharpe_dist" in p for p in paths)
        assert any("null_pvalues" in p for p in paths)
        for p in paths:
            assert Path(p).is_file()


def test_null_1_deterministic():
    """Same seed -> same random ranks."""
    signal_df, _ = _fixture(10, 5)
    n1 = null_1_random_ranks(signal_df, 99)
    n2 = null_1_random_ranks(signal_df, 99)
    pd.testing.assert_frame_equal(n1, n2)


def test_null_2_permutes_per_row():
    """Null 2 shuffles each row (same values, different order)."""
    signal_df, _ = _fixture(5, 4)
    out = null_2_permute_signal(signal_df, 7)
    for t in out.index:
        orig = signal_df.loc[t].dropna().sort_values()
        perm = out.loc[t].dropna().sort_values()
        if len(orig) >= 2:
            np.testing.assert_allclose(orig.values, perm.values)


def test_null_3_block_shuffle_reorders_rows():
    """Null 3 produces same rows in different order (block permutation)."""
    signal_df, _ = _fixture(20, 3)
    out = null_3_block_shuffle(signal_df, block_size=5, seed=11)
    assert out.shape == signal_df.shape
    assert set(out.index) == set(signal_df.index)
    # Content should be rows from original (possibly reordered)
    for t in out.index:
        row = out.loc[t]
        found = False
        for s in signal_df.index:
            if np.allclose(row.values, signal_df.loc[s].values, equal_nan=True):
                found = True
                break
        assert found


def test_under_null_false_positive_rate():
    """With random signal/returns, p-value should not be tiny (no true signal)."""
    signal_df, returns_df = _fixture(50, 12, seed=123)
    result = run_null_suite(signal_df, returns_df, n_sim=30, block_size=8, seed=456)
    # Under null, p_value_ic and p_value_sharpe are roughly uniform; expect not all < 0.01
    p_ic = list(result.p_value_ic.values())
    p_sharpe = list(result.p_value_sharpe.values())
    assert any(np.isfinite(p) for p in p_ic)
    assert any(np.isfinite(p) for p in p_sharpe)
    # At least one null type should have p_value not extremely small (would indicate bug)
    max_p_ic = max((p for p in p_ic if np.isfinite(p)), default=0)
    assert max_p_ic > 0.02 or not any(np.isfinite(p) for p in p_ic)
