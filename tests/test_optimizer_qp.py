"""Tests for constrained QP portfolio optimizer."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import pytest

try:
    import scipy  # noqa: F401
except ImportError:
    pytest.skip("scipy not available", allow_module_level=True)

from crypto_analyzer.optimizer import optimize_ls_qp


def _identity_cov(keys):
    """Build an identity covariance DataFrame for the given keys."""
    n = len(keys)
    return pd.DataFrame(np.eye(n), index=keys, columns=keys)


def test_higher_signal_gets_higher_weight():
    """Asset with the strongest positive signal receives the largest weight."""
    keys = ["A", "B", "C"]
    signal = pd.Series([3.0, 1.0, -2.0], index=keys)
    cov = _identity_cov(keys)
    w = optimize_ls_qp(signal, cov, gross_leverage=1.0, net_exposure=0.0, max_weight=0.5)
    assert w["A"] == max(w), "Highest-signal asset should get the highest weight"
    assert w["A"] > 0


def test_max_weight_respected():
    """No weight exceeds max_weight in absolute value."""
    keys = ["A", "B", "C", "D"]
    signal = pd.Series([5.0, 3.0, -1.0, -4.0], index=keys)
    cov = _identity_cov(keys)
    mw = 0.08
    w = optimize_ls_qp(signal, cov, gross_leverage=1.0, max_weight=mw)
    assert (w.abs() <= mw + 1e-6).all(), f"All |weights| must be <= {mw}"


def test_net_exposure_respected():
    """Sum of weights matches the requested net exposure."""
    keys = ["A", "B", "C", "D", "E"]
    signal = pd.Series([2.0, 1.0, 0.0, -1.0, -2.0], index=keys)
    cov = _identity_cov(keys)
    target_net = 0.05
    w = optimize_ls_qp(signal, cov, gross_leverage=1.0, net_exposure=target_net, max_weight=0.5)
    assert abs(w.sum() - target_net) < 1e-4, "Net exposure constraint violated"


def test_gross_leverage_respected():
    """Sum of absolute weights does not exceed gross leverage."""
    keys = ["A", "B", "C", "D"]
    signal = pd.Series([10.0, 5.0, -3.0, -8.0], index=keys)
    cov = _identity_cov(keys)
    gl = 0.5
    w = optimize_ls_qp(signal, cov, gross_leverage=gl, max_weight=0.5)
    assert w.abs().sum() <= gl + 1e-4, "Gross leverage constraint violated"


def test_long_only_no_negatives():
    """Long-only mode produces no negative weights."""
    keys = ["A", "B", "C"]
    signal = pd.Series([3.0, 1.0, -2.0], index=keys)
    cov = _identity_cov(keys)
    w = optimize_ls_qp(signal, cov, long_only=True, max_weight=0.5)
    assert (w >= -1e-8).all(), "Long-only should produce no negative weights"


def test_fallback_on_bad_cov():
    """Singular or empty covariance triggers fallback without crashing."""
    keys = ["A", "B", "C"]
    signal = pd.Series([1.0, 0.0, -1.0], index=keys)
    bad_cov = pd.DataFrame(np.zeros((3, 3)), index=keys, columns=keys)
    w = optimize_ls_qp(signal, bad_cov, gross_leverage=1.0)
    assert len(w) > 0, "Should return weights even with degenerate cov"
    assert np.isfinite(w).all(), "All fallback weights must be finite"


def test_deterministic():
    """Identical inputs produce identical outputs."""
    keys = ["A", "B", "C", "D"]
    signal = pd.Series([2.0, 1.0, -1.0, -2.0], index=keys)
    cov = _identity_cov(keys)
    kwargs = dict(gross_leverage=1.0, net_exposure=0.0, max_weight=0.4)
    w1 = optimize_ls_qp(signal, cov, **kwargs)
    w2 = optimize_ls_qp(signal, cov, **kwargs)
    pd.testing.assert_series_equal(w1, w2)
