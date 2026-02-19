"""Tests for cross-sectional factor construction (cs_factors)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from crypto_analyzer.cs_factors import (
    build_cs_factor_frame,
    cs_zscore,
    safe_log,
    winsorize_series,
)

N_ASSETS = 5
N_TIMESTAMPS = 50


def _make_bars() -> pd.DataFrame:
    """Synthetic bars for 5 assets over 50 hourly timestamps."""
    np.random.seed(7)
    ts = pd.date_range("2024-01-01", periods=N_TIMESTAMPS, freq="1h")
    rows = []
    for i in range(N_ASSETS):
        cid = "eth"
        addr = f"0xpair{i}"
        liquidity = 1e6 * (i + 1) + np.random.randn(N_TIMESTAMPS) * 1e3
        vol = 5e5 * (i + 1) + np.random.randn(N_TIMESTAMPS) * 1e2
        log_ret = np.random.randn(N_TIMESTAMPS) * 0.02
        close = 100 * np.exp(np.cumsum(log_ret))
        for t_idx in range(N_TIMESTAMPS):
            rows.append(
                {
                    "ts_utc": ts[t_idx],
                    "chain_id": cid,
                    "pair_address": addr,
                    "close": close[t_idx],
                    "log_return": log_ret[t_idx],
                    "liquidity_usd": liquidity[t_idx],
                    "vol_h24": vol[t_idx],
                }
            )
    return pd.DataFrame(rows)


def test_safe_log_handles_zeros():
    """Zero and negative inputs become NaN; positive inputs get logged."""
    s = pd.Series([0.0, -1.0, 1.0, np.e, 100.0])
    result = safe_log(s)
    assert np.isnan(result.iloc[0])
    assert np.isnan(result.iloc[1])
    assert np.isclose(result.iloc[2], 0.0)
    assert np.isclose(result.iloc[3], 1.0)


def test_winsorize_clips_outliers():
    """Extreme values are clipped to the p / 1-p quantiles."""
    np.random.seed(8)
    s = pd.Series(np.random.randn(200))
    s.iloc[0] = 100.0
    s.iloc[1] = -100.0
    w = winsorize_series(s, p=0.01)
    assert w.max() < 100.0
    assert w.min() > -100.0


def test_cs_zscore_mean_std():
    """Z-scored series has mean~0 and std~1."""
    np.random.seed(9)
    s = pd.Series(np.random.randn(20) * 5 + 10)
    z = cs_zscore(s)
    assert abs(z.mean()) < 1e-10
    assert abs(z.std(ddof=1) - 1.0) < 1e-10


def test_cs_zscore_few_values():
    """Fewer than 3 values yields all NaN."""
    z = cs_zscore(pd.Series([1.0, 2.0]))
    assert z.isna().all()


def test_cs_zscore_constant():
    """Constant series (std==0) yields all NaN."""
    z = cs_zscore(pd.Series([5.0, 5.0, 5.0, 5.0]))
    assert z.isna().all()


def test_build_cs_factor_frame_shape():
    """Output has expected long-form shape and factor names."""
    bars = _make_bars()
    out = build_cs_factor_frame(bars, freq="1h", lookback=6)
    assert set(out.columns) == {"ts_utc", "pair_key", "factor_name", "value"}
    assert set(out["factor_name"].unique()) == {"size_factor", "liquidity_factor", "momentum_factor"}
    n_ts = out["ts_utc"].nunique()
    assert len(out) == n_ts * N_ASSETS * 3


def test_build_cs_factor_frame_pair_key_format():
    """pair_key follows chain_id:pair_address format."""
    bars = _make_bars()
    out = build_cs_factor_frame(bars, freq="1h", lookback=6)
    for pk in out["pair_key"].unique():
        parts = pk.split(":")
        assert len(parts) == 2
        assert parts[0] == "eth"


def test_build_cs_factor_frame_zscore_stats():
    """When zscore=True, each (ts, factor) group has mean~0 and std~1."""
    bars = _make_bars()
    out = build_cs_factor_frame(bars, freq="1h", lookback=6, zscore=True)
    for (ts, fn), grp in out.groupby(["ts_utc", "factor_name"]):
        vals = grp["value"].dropna()
        if len(vals) < 3:
            continue
        assert abs(vals.mean()) < 1e-8, f"mean != 0 at {ts}, {fn}"
        assert abs(vals.std(ddof=1) - 1.0) < 1e-8, f"std != 1 at {ts}, {fn}"


def test_build_cs_factor_frame_no_zscore():
    """zscore=False skips standardization; raw winsorized values returned."""
    bars = _make_bars()
    out = build_cs_factor_frame(bars, freq="1h", lookback=6, zscore=False)
    mom = out[out["factor_name"] == "momentum_factor"]["value"].dropna()
    assert not mom.empty


def test_build_cs_factor_frame_momentum_alignment():
    """Momentum factor correlates with cumulative log-returns."""
    bars = _make_bars()
    lookback = 6
    out = build_cs_factor_frame(bars, freq="1h", lookback=lookback, zscore=False)
    mom = out[out["factor_name"] == "momentum_factor"]
    last_ts = mom["ts_utc"].max()
    snapshot = mom[mom["ts_utc"] == last_ts].set_index("pair_key")["value"]
    df = bars.copy()
    df["pair_key"] = df["chain_id"].astype(str) + ":" + df["pair_address"].astype(str)
    manual = df[df["ts_utc"] <= last_ts].groupby("pair_key")["log_return"].apply(lambda x: x.tail(lookback).sum())
    common = snapshot.index.intersection(manual.index)
    corr = np.corrcoef(snapshot.loc[common].values, manual.loc[common].values)[0, 1]
    assert corr > 0.9


def test_min_asset_requirement():
    """Timestamps with <3 assets are excluded."""
    bars = _make_bars()
    small = bars[bars["pair_address"].isin(["0xpair0", "0xpair1"])]
    out = build_cs_factor_frame(small, freq="1h", lookback=6)
    assert out.empty
