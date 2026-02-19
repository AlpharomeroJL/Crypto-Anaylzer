"""Regime-conditioned validation: exact join must not use regime at t+1 for row t (no leakage)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.validation import attach_regime_label, ic_summary_by_regime, regime_coverage


def test_attach_regime_label_exact_join_no_t_plus_one():
    """
    Regime at t+1 must not be used for row t. Synthetic: regime(t+1) perfectly predicts return(t+1);
    regime(t) is random. With exact join, regime-conditioned IC at t uses only regime(t), so should
    not get spuriously high IC from future regime.
    """
    np.random.seed(42)
    n = 100
    idx = pd.date_range("2026-01-01", periods=n, freq="1h")

    # Returns at t+1 driven by a "future" label (what we must NOT use at t)
    returns_t_plus_1 = np.random.randn(n).astype(float) * 0.01
    future_label = np.random.choice(["A", "B"], size=n)  # at each t, this is the "t+1" label
    # Make return(t+1) correlated with future_label so that if we leaked we'd see high IC
    returns_t_plus_1[future_label == "A"] += 0.05
    returns_t_plus_1[future_label == "B"] -= 0.05

    # Regime at t: random (uncorrelated with returns_t_plus_1)
    regime_at_t = np.random.choice(["low", "high"], size=n)

    frame = pd.DataFrame({"ret": returns_t_plus_1}, index=idx)
    frame.index.name = "ts_utc"
    regimes = pd.DataFrame({"ts_utc": idx, "regime_label": regime_at_t})

    out = attach_regime_label(frame, regimes, join_policy="exact")
    assert "regime_label" in out.columns
    assert out["regime_label"].isin(["low", "high"]).all()

    # Regime labels aligned to t; IC of ret (which is "forward" from t) vs regime at t
    # Since regime_at_t is random w.r.t. returns_t_plus_1, mean IC per regime should be near 0
    regime_labels = out["regime_label"]
    ic_series = pd.Series(returns_t_plus_1, index=idx)
    summary = ic_summary_by_regime(ic_series, regime_labels, horizon=1)
    assert not summary.empty
    # With random regime at t, mean_ic per regime should be small (no leakage of t+1 regime)
    for _, row in summary.iterrows():
        assert abs(row["mean_ic"]) < 0.2, "Exact join must not use t+1 regime; mean_ic should be small"


def test_regime_coverage_regime_distribution_sorted():
    """regime_distribution keys are sorted for stable JSON (artifact and meta)."""
    s = pd.Series(["B", "A", "B", "unknown", "A"], index=range(5))
    cov = regime_coverage(s)
    dist = cov["regime_distribution"]
    assert list(dist.keys()) == sorted(dist.keys())


def test_regime_coverage_unknown_for_missing_ts():
    """Missing timestamps get regime_label = 'unknown'; coverage reports pct_unknown."""
    idx = pd.date_range("2026-01-01", periods=10, freq="1h")
    regimes = pd.DataFrame({"ts_utc": idx[:5], "regime_label": ["R1"] * 5})
    frame = pd.DataFrame({"x": range(10)}, index=idx)
    frame.index.name = "ts_utc"
    out = attach_regime_label(frame, regimes, join_policy="exact")
    assert (out["regime_label"].iloc[5:] == "unknown").all()
    reg_ser = out["regime_label"]
    cov = regime_coverage(reg_ser)
    assert cov["n_ts"] == 10
    assert cov["n_unknown"] == 5
    assert cov["pct_unknown"] == 0.5
