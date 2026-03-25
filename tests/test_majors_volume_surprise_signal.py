"""majors_venue_volume_surprise_research_v1: participation proxy from venue volume only."""

from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_analyzer.signals_xs import majors_venue_volume_surprise_research_v1


def test_volume_surprise_causal_shift_and_cross_section():
    idx = pd.date_range("2025-01-01", periods=30, freq="h", tz="UTC")
    cols = ["A-USD", "B-USD"]
    returns_df = pd.DataFrame(0.0, index=idx, columns=cols)
    # Volume: flat then spike on A at last bar only
    vol = pd.DataFrame(100.0, index=idx, columns=cols)
    vol.loc[idx[-1], "A-USD"] = 10000.0
    sig = majors_venue_volume_surprise_research_v1(returns_df, vol, "1h")
    assert not sig.empty
    last = sig.loc[idx[-1]].dropna()
    assert "A-USD" in last.index
    # Spike asset should get a finite score after z-score and negation
    assert np.isfinite(float(last["A-USD"]))


def test_volume_surprise_empty_volume_returns_empty_shape():
    idx = pd.date_range("2025-01-01", periods=5, freq="h", tz="UTC")
    returns_df = pd.DataFrame(0.0, index=idx, columns=["X-USD"])
    out = majors_venue_volume_surprise_research_v1(returns_df, pd.DataFrame(), "1h")
    assert out.shape == returns_df.shape
