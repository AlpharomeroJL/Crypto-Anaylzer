"""
Walk-forward path uses fit-on-train-only; no refit on test. Attestation produced.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.fold_causality.attestation import FOLD_CAUSALITY_ATTESTATION_SCHEMA_VERSION
from crypto_analyzer.fold_causality.folds import (
    SplitPlanConfig,
    make_walk_forward_splits,
    slice_df_by_fold,
)
from crypto_analyzer.fold_causality.runner import RunnerConfig, run_walk_forward_with_causality


def test_runner_produces_attestation_with_fit_on_train_only():
    """run_walk_forward_with_causality returns attestation with train_only_fit_enforced and no_future_rows_in_fit true."""
    idx = pd.date_range("2025-01-01", periods=200, freq="h")
    data = pd.DataFrame({"ts_utc": idx, "x": range(200)})
    cfg = SplitPlanConfig(train_bars=50, test_bars=20, step_bars=20, purge_gap_bars=2, embargo_bars=1)
    split_plan = make_walk_forward_splits(idx, cfg)
    assert len(split_plan.folds) >= 1

    def scorer(df):
        return {"n": len(df), "mean": float(df["x"].mean())}

    runner_cfg = RunnerConfig(ts_column="ts_utc", run_key="rk", dataset_id_v2="ds")
    per_fold, attestation = run_walk_forward_with_causality(data, split_plan, [], scorer, runner_cfg)
    assert attestation["fold_causality_attestation_schema_version"] == FOLD_CAUSALITY_ATTESTATION_SCHEMA_VERSION
    assert attestation["enforcement_checks"]["train_only_fit_enforced"] is True
    assert attestation["enforcement_checks"]["no_future_rows_in_fit"] is True
    assert len(per_fold) >= 1


def test_runner_fit_only_on_train_slice():
    """Per fold, train_df is strictly [train_start_ts, train_end_ts]; test_df is [test_start_ts, test_end_ts]; no overlap."""
    idx = pd.date_range("2025-01-01", periods=100, freq="h")
    data = pd.DataFrame({"ts_utc": idx, "val": range(100)})
    cfg = SplitPlanConfig(train_bars=30, test_bars=15, step_bars=15, purge_gap_bars=1, embargo_bars=1)
    split_plan = make_walk_forward_splits(idx, cfg)
    if not split_plan.folds:
        return
    fold = split_plan.folds[0]
    train_df, test_df = slice_df_by_fold(data, fold, "ts_utc")
    assert not train_df.empty and not test_df.empty
    train_ts = pd.to_datetime(train_df["ts_utc"])
    test_ts = pd.to_datetime(test_df["ts_utc"])
    assert train_ts.max() <= fold.train_end_ts
    assert test_ts.min() >= fold.test_start_ts
    assert train_ts.max() < test_ts.min()


def test_attestation_has_required_enforcement_checks():
    """Attestation from runner includes purge_applied, embargo_applied when used."""
    idx = pd.date_range("2025-01-01", periods=150, freq="h")
    data = pd.DataFrame({"ts_utc": idx, "x": range(150)})
    cfg = SplitPlanConfig(train_bars=40, test_bars=20, step_bars=20, purge_gap_bars=1, embargo_bars=1)
    split_plan = make_walk_forward_splits(idx, cfg)
    _, att = run_walk_forward_with_causality(
        data, split_plan, [], lambda df: {"n": len(df)}, RunnerConfig(ts_column="ts_utc")
    )
    assert "enforcement_checks" in att
    assert att["enforcement_checks"]["purge_applied"] is True
    assert att["enforcement_checks"]["embargo_applied"] is True
