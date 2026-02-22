"""
Runtime causality guards: assert no future rows in fit, train_df max ts <= fold.train_end_ts.
"""

from __future__ import annotations

from typing import Union

import pandas as pd

from .folds import FoldSpec


def _to_ts(x: Union[pd.Timestamp, str]) -> pd.Timestamp:
    if isinstance(x, pd.Timestamp):
        return x
    return pd.Timestamp(x)


class CausalityGuard:
    """
    Lightweight guard: during fit(train_df), assert train_df max timestamp <= fold.train_end_ts.
    Use in runner when calling transform.fit(train_df) to enforce no future leakage.
    """

    def __init__(self, fold: FoldSpec, ts_column: str = "ts_utc"):
        self.fold = fold
        self.ts_column = ts_column
        self._train_end_ts = _to_ts(fold.train_end_ts)

    def assert_train_bounds(self, train_df: pd.DataFrame) -> None:
        """Raise AssertionError if any row in train_df has timestamp > fold.train_end_ts."""
        if train_df.empty:
            return
        if self.ts_column not in train_df.columns:
            return  # no column to check
        ser = pd.to_datetime(train_df[self.ts_column])
        max_ts = ser.max()
        if max_ts > self._train_end_ts:
            raise AssertionError(
                f"CausalityGuard: train_df max timestamp {max_ts} > fold.train_end_ts {self._train_end_ts}"
            )
