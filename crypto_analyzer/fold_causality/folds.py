"""
Fold boundary contract for walk-forward: FoldSpec, SplitPlan, deterministic make_walk_forward_splits.
Purge and embargo enforced; asof_lag_bars applied to boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

import numpy as np
import pandas as pd

SPLIT_PLAN_SCHEMA_VERSION = 1


@dataclass
class FoldSpec:
    """
    Single fold boundary contract. All timestamps are inclusive where applicable.
    purge_gap_bars: gap between train_end and test_start (train_end moves earlier by purge).
    embargo_bars: additional gap after purge before test_start (test_start moves later).
    asof_lag_bars: lag for point-in-time; test scoring uses data up to test_end - asof_lag_bars.
    """

    fold_id: str
    train_start_ts: Union[pd.Timestamp, np.datetime64, str]
    train_end_ts: Union[pd.Timestamp, np.datetime64, str]
    test_start_ts: Union[pd.Timestamp, np.datetime64, str]
    test_end_ts: Union[pd.Timestamp, np.datetime64, str]
    purge_gap_bars: int
    embargo_bars: int
    asof_lag_bars: int
    horizon: Optional[Union[str, int]] = None


@dataclass
class SplitPlanConfig:
    """Config for make_walk_forward_splits. Bar counts; purge/embargo in bars."""

    train_bars: int
    test_bars: int
    step_bars: int = 1
    purge_gap_bars: int = 0
    embargo_bars: int = 0
    asof_lag_bars: int = 0
    expanding: bool = True
    min_train_bars: Optional[int] = None  # if set, first fold must have at least this many train bars
    horizon: Optional[Union[str, int]] = None


@dataclass
class SplitPlan:
    """Plan of folds; schema version for contract."""

    folds: list[FoldSpec] = field(default_factory=list)
    split_plan_schema_version: int = SPLIT_PLAN_SCHEMA_VERSION


def _to_ts(x: Union[pd.Timestamp, np.datetime64, str]) -> pd.Timestamp:
    if isinstance(x, pd.Timestamp):
        return x
    if isinstance(x, np.datetime64):
        return pd.Timestamp(x)
    return pd.Timestamp(x)


def make_walk_forward_splits(
    index_ts: Union[pd.DatetimeIndex, np.ndarray, pd.Series],
    cfg: SplitPlanConfig,
) -> SplitPlan:
    """
    Deterministic walk-forward splits with purge and embargo.
    Same inputs -> same folds. Train and test do not overlap; purge shrinks train_end;
    embargo pushes test_start later.
    """
    if hasattr(index_ts, "sort_values"):
        idx = index_ts.sort_values().drop_duplicates()
        times = np.asarray(idx)
    else:
        times = np.asarray(index_ts).ravel()
        times = np.unique(times)
        times = np.sort(times)
    n = len(times)
    train_bars = max(1, cfg.train_bars)
    test_bars = max(1, cfg.test_bars)
    step_bars = max(1, cfg.step_bars)
    purge = max(0, cfg.purge_gap_bars)
    embargo = max(0, cfg.embargo_bars)
    min_train = cfg.min_train_bars if cfg.min_train_bars is not None else train_bars
    if n < min_train + purge + embargo + test_bars:
        return SplitPlan(folds=[])
    folds_list: list[FoldSpec] = []
    train_end_pos = min_train if cfg.expanding else train_bars
    fold_index = 0
    while train_end_pos + purge + embargo + test_bars <= n:
        train_start_pos = 0 if cfg.expanding else (train_end_pos - train_bars)
        test_start_pos = train_end_pos + purge + embargo
        test_end_pos = test_start_pos + test_bars
        train_start_ts = _to_ts(times[train_start_pos])
        train_end_ts = _to_ts(times[train_end_pos - 1])
        test_start_ts = _to_ts(times[test_start_pos])
        test_end_ts = _to_ts(times[test_end_pos - 1])
        fold_id = f"fold_{fold_index}"
        folds_list.append(
            FoldSpec(
                fold_id=fold_id,
                train_start_ts=train_start_ts,
                train_end_ts=train_end_ts,
                test_start_ts=test_start_ts,
                test_end_ts=test_end_ts,
                purge_gap_bars=purge,
                embargo_bars=embargo,
                asof_lag_bars=cfg.asof_lag_bars,
                horizon=cfg.horizon,
            )
        )
        fold_index += 1
        train_end_pos += step_bars
    return SplitPlan(folds=folds_list, split_plan_schema_version=SPLIT_PLAN_SCHEMA_VERSION)


def slice_df_by_fold(
    df: pd.DataFrame,
    fold: FoldSpec,
    ts_column: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Return (train_df, test_df) for the fold. df must have ts_column (timestamp).
    Rows where ts in [train_start_ts, train_end_ts] -> train; [test_start_ts, test_end_ts] -> test.
    """
    train_start = _to_ts(fold.train_start_ts)
    train_end = _to_ts(fold.train_end_ts)
    test_start = _to_ts(fold.test_start_ts)
    test_end = _to_ts(fold.test_end_ts)
    if ts_column not in df.columns:
        raise ValueError(f"DataFrame missing timestamp column {ts_column!r}")
    ser = pd.to_datetime(df[ts_column])
    train_mask = (ser >= train_start) & (ser <= train_end)
    test_mask = (ser >= test_start) & (ser <= test_end)
    return df.loc[train_mask].copy(), df.loc[test_mask].copy()
