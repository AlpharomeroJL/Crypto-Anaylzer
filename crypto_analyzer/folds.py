"""
Purged walk-forward fold spec and split generation.
No overlap between train and test; embargo gap to avoid leakage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Union

import numpy as np


@dataclass
class FoldSpec:
    """Spec for purged walk-forward splits."""

    horizon: int  # test length (number of bars)
    embargo: int  # gap between train end and test start (bars)
    min_train: int  # minimum train length (bars)
    step: int = 1  # advance by this many bars per fold (>= 1)


def purged_walk_forward_splits(
    index: Union[np.ndarray, range],
    fold_spec: FoldSpec,
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """
    Return list of (train_idx, test_idx) as integer position arrays.
    index: 0..n-1 or array of length n (positions).
    No overlap: train and test for each fold are disjoint; embargo between train end and test start.
    """
    if hasattr(index, "__len__"):
        n = len(index)
    else:
        n = int(index.stop - index.start)  # type: ignore[union-attr]
    h = fold_spec.horizon
    e = fold_spec.embargo
    m = fold_spec.min_train
    s = max(1, fold_spec.step)
    if n < m + e + h or m < 1 or h < 1:
        return []
    out: List[Tuple[np.ndarray, np.ndarray]] = []
    train_end = m
    while train_end + e + h <= n:
        test_start = train_end + e
        test_end = test_start + h
        train_idx = np.arange(0, train_end, dtype=np.intp)
        test_idx = np.arange(test_start, test_end, dtype=np.intp)
        out.append((train_idx, test_idx))
        train_end += s
    return out
