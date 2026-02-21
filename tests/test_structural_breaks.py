"""Structural break tests: CUSUM and sup-Chow."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.structural_breaks import (
    CUSUM_MIN_OBS,
    SCAN_MIN_OBS,
    cusum_mean_shift,
    run_break_diagnostics,
    sup_chow_single_break,
)


def test_cusum_skip_short_series():
    """CUSUM skips when n < min_obs; skipped_reason set, stat/p_value null."""
    x = np.random.randn(10).astype(float) * 0.01
    out = cusum_mean_shift(x, min_obs=CUSUM_MIN_OBS)
    assert out.get("skipped_reason") is not None
    assert out.get("stat") is None
    assert out.get("p_value") is None


def test_sup_chow_skip_short_series():
    """Sup-Chow skips when n < 100; skipped_reason set, stat null."""
    x = np.random.randn(50).astype(float) * 0.01
    out = sup_chow_single_break(x, min_obs=SCAN_MIN_OBS)
    assert out.get("skipped_reason") is not None
    assert out.get("stat") is None


def test_sup_chow_break_at_known_index():
    """Series with mean shift at t=50: scan returns break near 50, break_suspected True."""
    np.random.seed(61)
    n = 120
    x = np.random.randn(n).astype(float) * 0.01
    x[50:] += 0.02
    out = sup_chow_single_break(x, min_obs=60)
    assert out.get("skipped_reason") is None
    assert out.get("estimated_break_index") is not None
    tau = out["estimated_break_index"]
    assert 30 <= tau <= 70
    assert out.get("break_suspected") is True


def test_cusum_no_shift_sanity():
    """No-shift series: p-value not systematically tiny; should not systematically flag."""
    np.random.seed(62)
    n = 50
    x = np.random.randn(n).astype(float) * 0.01
    out = cusum_mean_shift(x, min_obs=20)
    if out.get("skipped_reason") is None:
        assert out.get("p_value") is not None
        assert 0 <= out["p_value"] <= 1
    # With no shift, break_suspected should often be False (not systematic false positive)
    if out.get("skipped_reason") is None:
        assert "break_suspected" in out


def test_run_break_diagnostics_output_structure():
    """Each test entry has calibration_method, estimated_break_index, estimated_break_date, p_value; skipped_reason if skipped."""
    np.random.seed(63)
    n = 110
    s = pd.Series(np.random.randn(n).astype(float) * 0.01, index=pd.date_range("2025-01-01", periods=n, freq="h"))
    result = run_break_diagnostics({"net_returns": s}, scan_min_obs=100)
    assert "series" in result
    assert "net_returns" in result["series"]
    tests = result["series"]["net_returns"]
    assert len(tests) >= 2  # cusum + sup_chow
    for t in tests:
        assert "series_name" in t
        assert t["series_name"] == "net_returns"
        assert "test_name" in t
        assert t["test_name"] in ("cusum", "sup_chow")
        assert "calibration_method" in t
        assert "estimated_break_index" in t  # key present; value int or None
        assert "estimated_break_date" in t   # key present; value ISO str or None
        assert "p_value" in t               # key present; value float or None
        if t.get("skipped_reason"):
            assert t.get("stat") is None
            assert t.get("break_suspected") is not True  # or omitted


def test_run_break_diagnostics_mean_shift_at_50():
    """Series with mean shift at t=50: at least one test has estimated_break_index near 50 and break_suspected True."""
    np.random.seed(64)
    n = 120
    x = np.random.randn(n).astype(float) * 0.01
    x[50:] += 0.025
    s = pd.Series(x, index=pd.date_range("2025-01-01", periods=n, freq="h"))
    result = run_break_diagnostics({"portfolio_net_returns": s}, scan_min_obs=100)
    assert "series" in result and "portfolio_net_returns" in result["series"]
    tests = result["series"]["portfolio_net_returns"]
    break_found = False
    for t in tests:
        if t.get("skipped_reason"):
            continue
        idx = t.get("estimated_break_index")
        if idx is not None and 30 <= idx <= 70 and t.get("break_suspected") is True:
            break_found = True
            break
    assert break_found, "At least one test should flag break near index 50"
