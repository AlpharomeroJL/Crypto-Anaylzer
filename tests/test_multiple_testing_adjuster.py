"""Tests for MultipleTestingAdjuster (BH/BY)."""

from __future__ import annotations

import pandas as pd
import pytest

from crypto_analyzer.multiple_testing_adjuster import adjust


def test_bh_golden():
    """Known p-value vector: BH adjusted and discoveries match expected."""
    # Example: 5 p-values, q=0.05. BH: adj = p * n / rank (then min 1, enforce monotone)
    p = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05], index=["a", "b", "c", "d", "e"])
    adj, disc = adjust(p, method="bh", q=0.05)
    assert len(adj) == 5
    assert adj.index.equals(p.index)
    # Sorted: 0.01, 0.02, 0.03, 0.04, 0.05 -> ranks 1..5
    # adj = [0.01*5/1, 0.02*5/2, 0.03*5/3, 0.04*5/4, 0.05*5/5] = [0.05, 0.05, 0.05, 0.05, 0.05]
    assert list(adj.sort_values().values) == pytest.approx([0.05] * 5, abs=1e-9)
    assert disc.sum() >= 1
    assert (adj <= 0.05).sum() == disc.sum()


def test_by_more_conservative_than_bh():
    """BY adjusted p-values >= BH for same inputs."""
    p = pd.Series([0.01, 0.03, 0.05, 0.07, 0.09], index=list("abcde"))
    adj_bh, _ = adjust(p, method="bh", q=0.05)
    adj_by, _ = adjust(p, method="by", q=0.05)
    assert (adj_by >= adj_bh).all()


def test_adjust_monotonicity():
    """Adjusted p-values are monotone in original p-values (BH/BY)."""
    p = pd.Series([0.5, 0.01, 0.2, 0.1], index=[0, 1, 2, 3])
    adj, _ = adjust(p, method="bh", q=0.2)
    # After sorting by p: 0.01, 0.1, 0.2, 0.5 -> adj non-decreasing
    sorted_p = p.sort_values()
    adj_by_p = adj.loc[sorted_p.index].values
    for i in range(1, len(adj_by_p)):
        assert adj_by_p[i] >= adj_by_p[i - 1] - 1e-12


def test_adjust_reproducible():
    """Same inputs -> same outputs (family-level stable)."""
    p = pd.Series([0.02, 0.04, 0.06, 0.08], index=["s1_h1", "s1_h2", "s2_h1", "s2_h2"])
    adj1, disc1 = adjust(p, method="bh", q=0.05)
    adj2, disc2 = adjust(p, method="bh", q=0.05)
    pd.testing.assert_series_equal(adj1, adj2)
    pd.testing.assert_series_equal(disc1, disc2)


def test_no_family_empty_unchanged():
    """Empty p_values -> empty adjusted and no discoveries."""
    p = pd.Series(dtype=float)
    adj, disc = adjust(p, method="bh", q=0.05)
    assert adj.empty and disc.empty


def test_no_family_nan_handling():
    """NaN in p_values -> NaN in adjusted; not counted as discovery."""
    p = pd.Series([0.01, float("nan"), 0.05], index=["a", "b", "c"])
    adj, disc = adjust(p, method="bh", q=0.05)
    assert pd.isna(adj["b"])
    assert not disc["b"]
    assert adj["a"] <= 0.05
    assert adj["c"] <= 0.05
