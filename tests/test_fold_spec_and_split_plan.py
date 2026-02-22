"""
FoldSpec and SplitPlan: deterministic fold ids, purge/embargo correctness, no leakage.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_analyzer.fold_causality.folds import (
    SplitPlan,
    SplitPlanConfig,
    make_walk_forward_splits,
    slice_df_by_fold,
)


def test_make_walk_forward_splits_deterministic():
    """Same inputs -> same folds (deterministic)."""
    n = 100
    index_ts = pd.date_range("2020-01-01", periods=n, freq="h")
    cfg = SplitPlanConfig(train_bars=30, test_bars=10, step_bars=10, purge_gap_bars=2, embargo_bars=1)
    plan1 = make_walk_forward_splits(index_ts, cfg)
    plan2 = make_walk_forward_splits(index_ts, cfg)
    assert len(plan1.folds) == len(plan2.folds)
    for f1, f2 in zip(plan1.folds, plan2.folds):
        assert f1.fold_id == f2.fold_id
        assert f1.train_end_ts == f2.train_end_ts
        assert f1.test_start_ts == f2.test_start_ts


def test_fold_ids_deterministic():
    """Fold ids are deterministic (fold_0, fold_1, ...)."""
    index_ts = pd.date_range("2020-01-01", periods=80, freq="h")
    cfg = SplitPlanConfig(train_bars=20, test_bars=10, step_bars=10)
    plan = make_walk_forward_splits(index_ts, cfg)
    for i, f in enumerate(plan.folds):
        assert f.fold_id == f"fold_{i}"


def test_purge_embargo_correctness():
    """Purge moves train_end earlier; embargo moves test_start later; no overlap."""
    n = 100
    index_ts = pd.date_range("2020-01-01", periods=n, freq="h")
    purge = 3
    embargo = 2
    cfg = SplitPlanConfig(
        train_bars=25,
        test_bars=10,
        step_bars=15,
        purge_gap_bars=purge,
        embargo_bars=embargo,
    )
    plan = make_walk_forward_splits(index_ts, cfg)
    assert len(plan.folds) >= 1
    times = pd.DatetimeIndex(index_ts)
    for f in plan.folds:
        train_end_ts = pd.Timestamp(f.train_end_ts)
        test_start_ts = pd.Timestamp(f.test_start_ts)
        train_end_pos = times.get_indexer([train_end_ts], method="ffill")[0]
        test_start_pos = times.get_indexer([test_start_ts], method="bfill")[0]
        gap = test_start_pos - train_end_pos - 1
        assert gap == purge + embargo, f"expected gap purge+embargo={purge + embargo}, got {gap}"


def test_fold_ranges_non_overlapping():
    """Train and test ranges do not overlap; test follows train."""
    index_ts = pd.date_range("2020-01-01", periods=120, freq="h")
    cfg = SplitPlanConfig(train_bars=40, test_bars=15, step_bars=20, purge_gap_bars=1, embargo_bars=1)
    plan = make_walk_forward_splits(index_ts, cfg)
    for f in plan.folds:
        train_end = pd.Timestamp(f.train_end_ts)
        test_start = pd.Timestamp(f.test_start_ts)
        assert test_start > train_end
        train_start = pd.Timestamp(f.train_start_ts)
        test_end = pd.Timestamp(f.test_end_ts)
        assert train_start < train_end
        assert test_start < test_end


def test_slice_df_by_fold():
    """slice_df_by_fold returns train and test subsets by timestamp."""
    n = 60
    df = pd.DataFrame(
        {
            "ts_utc": pd.date_range("2020-01-01", periods=n, freq="h"),
            "x": np.arange(n, dtype=float),
        }
    )
    cfg = SplitPlanConfig(train_bars=20, test_bars=10, step_bars=10)
    plan = make_walk_forward_splits(df["ts_utc"], cfg)
    assert len(plan.folds) >= 1
    fold = plan.folds[0]
    train_df, test_df = slice_df_by_fold(df, fold, "ts_utc")
    assert len(train_df) == 20
    assert len(test_df) == 10
    assert train_df["ts_utc"].max() <= fold.train_end_ts
    assert test_df["ts_utc"].min() >= fold.test_start_ts
    assert train_df["ts_utc"].max() < pd.Timestamp(test_df["ts_utc"].min())


def test_split_plan_schema_version():
    """SplitPlan has split_plan_schema_version = 1."""
    from crypto_analyzer.fold_causality.folds import SPLIT_PLAN_SCHEMA_VERSION

    plan = SplitPlan(folds=[], split_plan_schema_version=SPLIT_PLAN_SCHEMA_VERSION)
    assert plan.split_plan_schema_version == 1
