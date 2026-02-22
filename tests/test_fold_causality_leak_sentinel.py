"""
Leak sentinel: synthetic data where test has a future shock; trainable transform must fit on train only.
If transform is incorrectly fit on full data, contamination is detectable; test must assert no leakage.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_analyzer.fold_causality.folds import (
    SplitPlanConfig,
    make_walk_forward_splits,
)
from crypto_analyzer.fold_causality.runner import RunnerConfig, run_walk_forward_with_causality
from crypto_analyzer.fold_causality.transforms import TrainState


class ZScoreNormalizeTrainable:
    """Fit mean/std on train; transform using those stats. Must not see test during fit."""

    def __init__(self, column: str = "x"):
        self.column = column
        self._mean = None
        self._std = None

    def fit(self, train_df: pd.DataFrame) -> TrainState:
        if self.column not in train_df.columns:
            return TrainState(_payload={})
        ser = train_df[self.column].astype(float)
        self._mean = float(ser.mean())
        self._std = float(ser.std()) if ser.std() > 0 else 1.0
        return TrainState(_payload={"mean": self._mean, "std": self._std})

    def transform(self, df: pd.DataFrame, state: TrainState) -> pd.DataFrame:
        out = df.copy()
        if self.column not in out.columns or not state._payload:
            return out
        m = state._payload.get("mean", 0.0)
        s = state._payload.get("std", 1.0)
        out[self.column] = (out[self.column].astype(float) - m) / s
        return out


def _make_sentinel_series(n_train: int, n_test: int, test_spike: float) -> pd.DataFrame:
    """Train: near 0; test: huge spike. If fit includes test, mean/std are contaminated."""
    n = n_train + n_test
    ts = pd.date_range("2020-01-01", periods=n, freq="h")
    x = np.zeros(n, dtype=float)
    x[n_train:] = test_spike
    return pd.DataFrame({"ts_utc": ts, "x": x})


def test_leak_sentinel_train_only_stats():
    """Train-only fit: computed train stats match train-only; test transformed with train stats."""
    n_train, n_test = 50, 20
    test_spike = 100.0
    df = _make_sentinel_series(n_train, n_test, test_spike)
    train_df = df.iloc[:n_train]
    test_df = df.iloc[n_train:]
    transform = ZScoreNormalizeTrainable(column="x")
    state = transform.fit(train_df)
    train_mean = train_df["x"].mean()
    train_std = train_df["x"].std() if train_df["x"].std() > 0 else 1.0
    assert state._payload.get("mean") == train_mean
    assert state._payload.get("std") == train_std
    test_out = transform.transform(test_df, state)
    expected_test_z = (test_df["x"].values - train_mean) / train_std
    np.testing.assert_array_almost_equal(test_out["x"].values, expected_test_z)
    assert np.allclose(test_out["x"].iloc[0], test_spike / train_std)


def test_leak_sentinel_contamination_detectable():
    """If we fit on full data (leak), train stats differ from train-only; test transformed values differ."""
    n_train, n_test = 50, 20
    test_spike = 100.0
    df = _make_sentinel_series(n_train, n_test, test_spike)
    train_only = df.iloc[:n_train]
    full = df
    t_train = ZScoreNormalizeTrainable(column="x")
    t_full = ZScoreNormalizeTrainable(column="x")
    state_train = t_train.fit(train_only)
    state_full = t_full.fit(full)
    assert state_full._payload.get("mean") != state_train._payload.get("mean")
    test_df = df.iloc[n_train:]
    out_train = t_train.transform(test_df, state_train)
    out_full = t_full.transform(test_df, state_full)
    assert not np.allclose(out_train["x"].values, out_full["x"].values)


def test_leak_sentinel_runner_fit_on_train_only():
    """run_walk_forward_with_causality fits on train only; attestation has no_future_rows_in_fit true."""
    # Need n >= train_bars + purge + embargo + test_bars (40+2+1+20=63)
    n_train, n_test = 40, 23
    df = _make_sentinel_series(n_train, n_test, test_spike=50.0)
    test_bars = 20
    cfg = SplitPlanConfig(
        train_bars=n_train,
        test_bars=test_bars,
        step_bars=test_bars,
        purge_gap_bars=2,
        embargo_bars=1,
        expanding=True,
    )
    index_ts = df["ts_utc"]
    split_plan = make_walk_forward_splits(index_ts, cfg)
    assert len(split_plan.folds) >= 1, "need at least one fold (n >= train+purge+embargo+test)"
    transforms = [("zscore", ZScoreNormalizeTrainable(column="x"))]

    def scorer(d: pd.DataFrame) -> dict:
        return {"mean": float(d["x"].mean()), "n": len(d)}

    runner_cfg = RunnerConfig(ts_column="ts_utc", run_key="leak_sentinel_rk", dataset_id_v2="ds1")
    results, attestation = run_walk_forward_with_causality(df, split_plan, transforms, scorer, runner_cfg)
    assert attestation["enforcement_checks"]["train_only_fit_enforced"] is True
    assert attestation["enforcement_checks"]["no_future_rows_in_fit"] is True
    assert len(results) >= 1
    fold0 = results[0]
    assert "metrics" in fold0
    assert fold0["metrics"]["n"] == test_bars, "test fold should have test_bars rows"
