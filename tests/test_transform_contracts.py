"""
Transform contracts: trainable requires fit before transform; exogenous has no fit/state.
"""

from __future__ import annotations

import pandas as pd
import pytest

from crypto_analyzer.fold_causality.transforms import (
    TRANSFORM_REGISTRY,
    ExogenousTransform,
    TrainState,
    TransformSpec,
)


class NoOpExogenous:
    """Exogenous: transform only, no fit."""

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.copy()


class ZScoreTrainable:
    """Trainable: fit on train, transform with state."""

    def __init__(self, col: str = "x"):
        self.col = col

    def fit(self, train_df: pd.DataFrame) -> TrainState:
        if self.col not in train_df.columns:
            return TrainState(_payload={})
        m = train_df[self.col].mean()
        s = train_df[self.col].std() or 1.0
        return TrainState(_payload={"mean": m, "std": s})

    def transform(self, df: pd.DataFrame, state: TrainState) -> pd.DataFrame:
        out = df.copy()
        if self.col in out.columns and state._payload:
            m, s = state._payload["mean"], state._payload["std"]
            out[self.col] = (out[self.col] - m) / s
        return out


def test_exogenous_has_no_fit():
    """Exogenous transform does not require fit; transform only."""
    t: ExogenousTransform = NoOpExogenous()
    df = pd.DataFrame({"a": [1, 2, 3]})
    out = t.transform(df)
    assert out is not df
    pd.testing.assert_frame_equal(out, df)
    assert not hasattr(t, "fit") or not callable(getattr(t, "fit", None))


def test_trainable_requires_fit_before_transform():
    """Trainable transform requires fit(train_df) before transform(df, state)."""
    t = ZScoreTrainable(col="x")
    train_df = pd.DataFrame({"x": [1.0, 2.0, 3.0]})
    state = t.fit(train_df)
    assert state._payload.get("mean") == 2.0
    test_df = pd.DataFrame({"x": [4.0, 5.0]})
    out = t.transform(test_df, state)
    assert out["x"].iloc[0] == pytest.approx(2.0)  # (4-2)/1 = 2
    assert out["x"].iloc[1] == pytest.approx(3.0)


def test_trainable_transform_without_state_fails_semantically():
    """Transform with empty state yields no normalization (state must come from fit)."""
    t = ZScoreTrainable(col="x")
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0]})
    empty_state = TrainState(_payload={})
    out = t.transform(df, empty_state)
    pd.testing.assert_series_equal(out["x"], df["x"])


def test_transform_spec_to_dict():
    """TransformSpec serializes for attestation."""
    spec = TransformSpec(name="zscore", kind="trainable", version=1, params_hash="abc")
    d = spec.to_dict()
    assert d["name"] == "zscore"
    assert d["kind"] == "trainable"
    assert d["version"] == 1
    assert d["params_hash"] == "abc"


def test_registry_can_store_and_retrieve():
    """TRANSFORM_REGISTRY maps name -> (spec, impl)."""
    spec = TransformSpec(name="noop_exo", kind="exogenous", version=1)
    TRANSFORM_REGISTRY["noop_exo"] = (spec, NoOpExogenous())
    retrieved_spec, retrieved_impl = TRANSFORM_REGISTRY["noop_exo"]
    assert retrieved_spec.name == "noop_exo"
    assert retrieved_spec.kind == "exogenous"
    df = pd.DataFrame({"a": [1]})
    assert retrieved_impl.transform(df).equals(df)
    del TRANSFORM_REGISTRY["noop_exo"]
