"""Unit tests for liquidity_shock_reversion signal (case study)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from crypto_analyzer.signals_xs import (
    liquidity_shock_reversion_single,
    liquidity_shock_reversion_variants,
)

N_TS = 30
N_COLS = 5


def test_empty_liquidity_returns_empty():
    """Empty liquidity panel -> empty DataFrame from single; empty dict from variants."""
    idx = pd.date_range("2024-01-01", periods=N_TS, freq="1h")
    cols = pd.Index([f"chain:addr{i}" for i in range(N_COLS)])
    empty = pd.DataFrame()
    assert empty.empty
    out_single = liquidity_shock_reversion_single(
        liquidity_panel=empty,
        target_index=idx,
        target_columns=cols,
        N=6,
    )
    assert out_single.shape == (N_TS, N_COLS)
    assert out_single.isna().all().all()

    out_variants = liquidity_shock_reversion_variants(
        liquidity_panel=empty,
        target_index=idx,
        target_columns=cols,
    )
    assert out_variants == {}


def test_none_liquidity_returns_empty():
    """None liquidity -> empty output."""
    idx = pd.date_range("2024-01-01", periods=N_TS, freq="1h")
    cols = pd.Index([f"chain:addr{i}" for i in range(N_COLS)])
    out_single = liquidity_shock_reversion_single(
        liquidity_panel=None,
        target_index=idx,
        target_columns=cols,
        N=6,
    )
    assert out_single.shape == (N_TS, N_COLS)
    assert out_single.isna().all().all()

    out_variants = liquidity_shock_reversion_variants(
        liquidity_panel=None,
        target_index=idx,
        target_columns=cols,
    )
    assert out_variants == {}


def test_alignment_to_target_index_columns():
    """Output has exactly target_index and target_columns."""
    idx = pd.date_range("2024-01-01", periods=N_TS, freq="1h")
    cols_liq = pd.Index([f"chain:addr{i}" for i in range(N_COLS)])
    liq = pd.DataFrame(
        np.random.uniform(1e5, 1e7, (N_TS, N_COLS)),
        index=idx,
        columns=cols_liq,
    )
    target_idx = idx[2:-2]
    target_cols = pd.Index(["chain:addr0", "chain:addr2", "chain:addr4"])
    out = liquidity_shock_reversion_single(
        liquidity_panel=liq,
        target_index=target_idx,
        target_columns=target_cols,
        N=6,
    )
    assert out.index.equals(target_idx)
    assert out.columns.equals(target_cols)

    variants = liquidity_shock_reversion_variants(
        liquidity_panel=liq,
        target_index=target_idx,
        target_columns=target_cols,
    )
    assert len(variants) == 16
    for name, df in variants.items():
        assert df.index.equals(target_idx), name
        assert df.columns.equals(target_cols), name
        assert name.startswith("liqshock_N"), name


def test_first_n_bars_nan_no_leakage():
    """First N rows are NaN (diff(N) requires N lags; no future data)."""
    idx = pd.date_range("2024-01-01", periods=N_TS, freq="1h")
    cols = pd.Index([f"chain:addr{i}" for i in range(N_COLS)])
    liq = pd.DataFrame(
        np.random.uniform(1e5, 1e7, (N_TS, N_COLS)),
        index=idx,
        columns=cols,
    )
    N = 6
    out = liquidity_shock_reversion_single(
        liquidity_panel=liq,
        target_index=idx,
        target_columns=cols,
        N=N,
    )
    assert out.iloc[:N].isna().all().all()
    assert out.iloc[N:].notna().any().any()


def test_sixteen_deterministic_variant_names():
    """Variants dict has exactly 16 keys with deterministic names."""
    idx = pd.date_range("2024-01-01", periods=N_TS, freq="1h")
    cols = pd.Index([f"c{i}" for i in range(3)])
    liq = pd.DataFrame(np.random.uniform(1e5, 1e7, (N_TS, 3)), index=idx, columns=cols)
    variants = liquidity_shock_reversion_variants(
        liquidity_panel=liq,
        target_index=idx,
        target_columns=cols,
    )
    assert len(variants) == 16
    expected_n = [6, 12, 24, 48]
    expected_p = [0.01, 0.05]
    expected_clip = [3, 5]
    seen = set()
    for name in variants:
        assert name.startswith("liqshock_N"), name
        for N in expected_n:
            if f"_N{N}_" in name:
                for p in expected_p:
                    if f"_w{p}_" in name:
                        for c in expected_clip:
                            if f"_clip{c}" in name:
                                seen.add((N, p, c))
                                break
    assert len(seen) == 16
