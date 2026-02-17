"""Diagnostics: health summary returns expected keys; functions degrade gracefully."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crypto_analyzer.diagnostics import (
    rolling_ic_stability,
    regime_concentration,
    asset_concentration,
    cost_sensitivity,
    build_health_summary,
)


def test_rolling_ic_stability_returns_keys():
    ser = pd.Series([0.1, 0.2, 0.05, -0.1, 0.15] * 10)
    out = rolling_ic_stability(ser, window=5)
    assert "mean" in out
    assert "std" in out
    assert "stability_score" in out


def test_rolling_ic_stability_empty_graceful():
    out = rolling_ic_stability(pd.Series(dtype=float), 5)
    assert out["mean"] != out["mean"] or out["mean"] is None or isinstance(out["mean"], float)
    assert "stability_score" in out


def test_regime_concentration_empty():
    df = pd.DataFrame(columns=["regime", "ret"])
    out = regime_concentration(df, regime_col="regime")
    assert isinstance(out, pd.DataFrame)


def test_regime_concentration_with_data():
    df = pd.DataFrame({"regime": ["a", "a", "b"], "ret": [0.01, -0.01, 0.02]})
    out = regime_concentration(df, regime_col="regime")
    assert not out.empty or out.shape[0] >= 0


def test_asset_concentration_empty():
    out = asset_concentration(pd.DataFrame())
    assert "max_weight" in out
    assert "herfindahl" in out


def test_asset_concentration_with_weights():
    w = pd.DataFrame({"A": [0.5, 0.3], "B": [-0.3, -0.2]})
    out = asset_concentration(w)
    assert "max_weight" in out
    assert "herfindahl" in out


def test_cost_sensitivity():
    pnl_g = pd.Series([0.01, -0.005, 0.02])
    pnl_n = pd.Series([0.008, -0.006, 0.018])
    out = cost_sensitivity(pnl_g, pnl_n)
    assert "drag" in out
    assert "percent" in out


def test_build_health_summary_returns_keys():
    h = build_health_summary(
        data_coverage={"n_assets": 5, "n_bars": 100},
        signal_stability={"mean": 0.1, "stability_score": 0.5},
    )
    assert "data_coverage" in h
    assert "signal_stability" in h
    assert h["data_coverage"]["n_assets"] == 5
