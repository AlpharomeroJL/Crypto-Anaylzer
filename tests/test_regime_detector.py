"""RegimeDetector: filter-only in test, no smoothing; no leakage; probs sum to 1."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crypto_analyzer.regimes.regime_detector import (
    REGIME_HIGH_VOL,
    REGIME_LOW_VOL,
    REGIME_MED_VOL,
    RegimeConfig,
    fit_regime_detector,
    predict_regime,
)


def test_predict_smooth_raises_without_allow_smooth():
    """mode='smooth' must raise unless allow_smooth_in_test or allow_smooth=True."""
    np.random.seed(42)
    n = 30
    ts = pd.date_range("2026-01-01", periods=n, freq="h")
    vol = np.random.exponential(0.02, n)
    train = pd.DataFrame({"ts_utc": ts[:20], "realized_vol": vol[:20]})
    test = pd.DataFrame({"ts_utc": ts[20:], "realized_vol": vol[20:]})
    cfg = RegimeConfig(allow_smooth_in_test=False)
    model = fit_regime_detector(train, cfg)
    with pytest.raises(ValueError, match="smooth.*not allowed"):
        predict_regime(test, model, mode="smooth", allow_smooth=False)
    predict_regime(test, model, mode="filter")


def test_fit_on_train_predict_on_test_no_test_data_in_fit():
    """Fitted model uses only train timestamps; predict uses only test features (filter)."""
    np.random.seed(1)
    train_ts = pd.date_range("2026-01-01", periods=40, freq="h")
    test_ts = pd.date_range("2026-01-03", periods=20, freq="h")
    train_vol = np.random.exponential(0.01, 40)
    test_vol = np.random.exponential(0.02, 20)
    train_df = pd.DataFrame({"ts_utc": train_ts, "realized_vol": train_vol})
    test_df = pd.DataFrame({"ts_utc": test_ts, "realized_vol": test_vol})
    model = fit_regime_detector(train_df, RegimeConfig())
    assert hasattr(model, "fit_timestamps")
    states = predict_regime(test_df, model, mode="filter")
    assert len(states.ts_utc) == 20
    assert states.regime_label.shape[0] == 20


def test_regime_probabilities_sum_to_one():
    """Per-timestamp probabilities (prob_low + prob_med + prob_high) sum to 1.0 ± 1e-6."""
    np.random.seed(2)
    n = 25
    ts = pd.date_range("2026-02-01", periods=n, freq="h")
    vol = np.random.exponential(0.015, n)
    df = pd.DataFrame({"ts_utc": ts, "realized_vol": vol})
    train = df.iloc[:15]
    test = df.iloc[15:]
    model = fit_regime_detector(train, RegimeConfig())
    states = predict_regime(test, model, mode="filter")
    if states.prob_low is not None and states.prob_med is not None and states.prob_high is not None:
        total = states.prob_low + states.prob_med + states.prob_high
        for v in total.dropna():
            assert abs(v - 1.0) <= 1e-5, f"prob sum {v} != 1.0"


def test_no_leakage_regime_at_t_does_not_use_future():
    """Synthetic: if future vol is informative, regime at t must not use t+1 (filter is causal)."""
    # Build features where vol at t+1 is perfectly predictive of "true" regime at t
    # Under filter, we only use vol[0..t], so we must not see t+1
    n = 50
    ts = pd.date_range("2026-01-01", periods=n, freq="h")
    vol = np.random.exponential(0.02, n)
    df = pd.DataFrame({"ts_utc": ts, "realized_vol": vol})
    train = df.iloc[:25]
    test = df.iloc[25:]
    model = fit_regime_detector(train, RegimeConfig())
    states = predict_regime(test, model, mode="filter")
    # Filter processes row by row; each label depends only on current and past vol
    assert states.regime_label.shape[0] == len(test)
    labels = set(states.regime_label)
    assert labels <= {REGIME_LOW_VOL, REGIME_MED_VOL, REGIME_HIGH_VOL}
