"""Tests for cross-sectional signal combiner (cs_model)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from crypto_analyzer.cs_model import combine_factors, signal_to_wide

N_ASSETS = 5
N_TIMESTAMPS = 10


def _make_factor_df() -> pd.DataFrame:
    """Synthetic long-form factor DataFrame for 5 assets, 10 timestamps."""
    np.random.seed(42)
    ts = pd.date_range("2024-01-01", periods=N_TIMESTAMPS, freq="1h")
    rows = []
    for t in ts:
        for i in range(N_ASSETS):
            pk = f"eth:0xpair{i}"
            rows.append({"ts_utc": t, "pair_key": pk, "factor_name": "size_factor", "value": np.random.randn()})
            rows.append({"ts_utc": t, "pair_key": pk, "factor_name": "liquidity_factor", "value": np.random.randn()})
            rows.append({"ts_utc": t, "pair_key": pk, "factor_name": "momentum_factor", "value": float(i)})
    return pd.DataFrame(rows)


def test_combine_linear_momentum_dominates():
    """Default weights give momentum 0.6 weight; signal order should follow momentum rank."""
    fdf = _make_factor_df()
    result = combine_factors(fdf, method="linear")
    assert set(result.columns) == {"ts_utc", "pair_key", "signal"}
    first_ts = result["ts_utc"].min()
    snap = result[result["ts_utc"] == first_ts].sort_values("signal")
    ranked_pairs = snap["pair_key"].tolist()
    assert ranked_pairs[-1] == "eth:0xpair4"


def test_combine_linear_custom_weights():
    """Custom all-zero weights for size/liquidity should make signal purely momentum."""
    fdf = _make_factor_df()
    w = {"size_factor": 0.0, "liquidity_factor": 0.0, "momentum_factor": 1.0}
    result = combine_factors(fdf, weights=w, method="linear")
    first_ts = result["ts_utc"].min()
    snap = result[result["ts_utc"] == first_ts].set_index("pair_key")
    for i in range(N_ASSETS):
        pk = f"eth:0xpair{i}"
        assert np.isclose(snap.loc[pk, "signal"], float(i))


def test_combine_rank_sum_deterministic():
    """Rank-sum produces deterministic, strictly ordered signals when factors differ."""
    fdf = _make_factor_df()
    result = combine_factors(fdf, method="rank_sum")
    assert "signal" in result.columns
    first_ts = result["ts_utc"].min()
    snap = result[result["ts_utc"] == first_ts]
    assert snap["signal"].nunique() >= 2


def test_min_asset_filter():
    """Timestamps with <3 assets are dropped."""
    fdf = _make_factor_df()
    sparse = fdf[fdf["pair_key"].isin(["eth:0xpair0", "eth:0xpair1"])]
    result = combine_factors(sparse, method="linear")
    assert result.empty


def test_signal_to_wide_pivot():
    """Pivot long-form signal to a wide matrix with correct shape."""
    fdf = _make_factor_df()
    sig = combine_factors(fdf, method="linear")
    wide = signal_to_wide(sig)
    assert wide.shape[0] == sig["ts_utc"].nunique()
    assert wide.shape[1] == sig["pair_key"].nunique()
    assert not wide.isnull().all().all()


def test_signal_to_wide_values():
    """Wide values match the original long-form signal values."""
    fdf = _make_factor_df()
    sig = combine_factors(fdf, method="linear")
    wide = signal_to_wide(sig)
    for _, row in sig.iterrows():
        assert np.isclose(wide.loc[row["ts_utc"], row["pair_key"]], row["signal"])
