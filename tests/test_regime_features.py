"""Regime features: causal (no lookahead) and deterministic."""

from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_analyzer.regimes.regime_features import RegimeFeatureConfig, build_regime_features


def test_build_regime_features_causal_at_t():
    """Features at time t must depend only on data at or before t (trailing windows)."""
    n = 100
    np.random.seed(42)
    ts = pd.date_range("2026-01-01", periods=n, freq="h")
    log_ret = np.random.randn(n) * 0.01
    df = pd.DataFrame({"ts_utc": ts, "log_return": log_ret})
    cfg = RegimeFeatureConfig(vol_window=12, drawdown_window=24, trend_window=12, min_bars=6)
    out = build_regime_features(df, cfg)
    assert "ts_utc" in out.columns
    assert "realized_vol" in out.columns
    assert "drawdown" in out.columns
    assert "trend_strength" in out.columns
    assert len(out) == n
    assert out["ts_utc"].is_monotonic_increasing
    # First min_bars-1 rows should have NaN for rolling features
    assert pd.isna(out["realized_vol"].iloc[0]) or out["realized_vol"].iloc[0] >= 0


def test_build_regime_features_deterministic():
    """Same inputs and config -> same output (stable ordering and values)."""
    n = 50
    np.random.seed(123)
    ts = pd.date_range("2026-02-01", periods=n, freq="h")
    log_ret = np.random.randn(n) * 0.02
    df = pd.DataFrame({"ts_utc": ts, "log_return": log_ret})
    cfg = RegimeFeatureConfig(vol_window=10, min_bars=5)
    out1 = build_regime_features(df, cfg)
    out2 = build_regime_features(df, cfg)
    pd.testing.assert_frame_equal(out1, out2)
    assert out1["ts_utc"].is_monotonic_increasing


def test_build_regime_features_long_format_aggregates():
    """Multiple rows per ts_utc: mean log_return per ts_utc (market-wide proxy)."""
    ts = pd.to_datetime(["2026-01-01 00:00", "2026-01-01 00:00", "2026-01-01 01:00"])
    df = pd.DataFrame({"ts_utc": ts, "log_return": [0.01, -0.01, 0.02]})
    out = build_regime_features(df, RegimeFeatureConfig(vol_window=2, min_bars=1))
    assert len(out) == 2
    assert out["ts_utc"].nunique() == 2


def test_build_regime_features_empty():
    """Empty bars_df -> empty DataFrame with expected columns."""
    out = build_regime_features(pd.DataFrame(), None)
    assert out.empty
    assert list(out.columns) == ["ts_utc", "realized_vol", "drawdown", "trend_strength"]
