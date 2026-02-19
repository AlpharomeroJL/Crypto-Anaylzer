"""Reality Check: under null, RC p-value not degenerate at 0 (smoke)."""

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
    run_reality_check,
)


def test_rc_under_null_not_always_tiny():
    """Under random (null-like) series, RC p-value should not be systematically 0 (smoke)."""
    np.random.seed(99)
    n = 80
    idx = pd.date_range("2025-01-01", periods=n, freq="h")
    series_by_hyp = {}
    for sig in ["s1", "s2"]:
        for h in [1]:
            series_by_hyp[f"{sig}|{h}"] = pd.Series(
                np.random.randn(n).astype(float) * 0.01, index=idx
            )
    observed = pd.Series(
        {hid: float(s.mean()) for hid, s in series_by_hyp.items()}
    ).sort_index()
    cfg = RealityCheckConfig(n_sim=30, seed=123, method="stationary", avg_block_length=10)
    null_gen = make_null_generator_stationary(series_by_hyp, cfg)
    result = run_reality_check(observed, null_gen, cfg)
    p = result["rc_p_value"]
    assert 0 <= p <= 1
    assert not (p == 0 and result["n_sim"] > 0)
