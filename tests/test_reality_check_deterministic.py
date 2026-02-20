"""Reality Check: determinism with fixed seed and observed stats."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.stats.reality_check import (
    RealityCheckConfig,
    make_null_generator_stationary,
    reality_check_pvalue,
    run_reality_check,
)


def test_rc_pvalue_formula():
    """RC p-value = (1 + count(T_b >= T_obs)) / (B+1)."""
    stat = pd.Series({"h1": 0.5, "h2": 0.3})
    null_matrix = np.array([[0.1, 0.2], [0.6, 0.1], [0.2, 0.4]])
    p = reality_check_pvalue(stat, null_matrix)
    T_obs = 0.5
    null_max = [0.2, 0.6, 0.4]
    count_ge = sum(1 for t in null_max if t >= T_obs)
    expected = (1 + count_ge) / 4.0
    assert abs(p - expected) < 1e-9


def test_reality_check_deterministic():
    """Same observed_stats + seed + n_sim -> identical rc_p_value and null_max."""
    np.random.seed(123)
    n = 60
    idx = pd.date_range("2025-01-01", periods=n, freq="h")
    s1 = pd.Series(np.random.randn(n).astype(float) * 0.01, index=idx)
    s2 = pd.Series(np.random.randn(n).astype(float) * 0.01, index=idx)
    series_by_hyp = {"a|1": s1, "b|1": s2}
    observed = pd.Series({"a|1": float(s1.mean()), "b|1": float(s2.mean())}).sort_index()
    cfg = RealityCheckConfig(n_sim=50, seed=42, method="stationary", avg_block_length=8)
    null_gen = make_null_generator_stationary(series_by_hyp, cfg)
    r1 = run_reality_check(observed, null_gen, cfg)
    r2 = run_reality_check(observed, null_gen, cfg)
    assert r1["rc_p_value"] == r2["rc_p_value"]
    np.testing.assert_array_almost_equal(r1["null_max_distribution"], r2["null_max_distribution"], decimal=12)
