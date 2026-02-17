"""Walk-forward split boundaries: no overlap, correct lengths."""
import pandas as pd
import pytest
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.walkforward import walk_forward_splits


def test_walk_forward_splits_rolling():
    """Rolling: train and test bars match; no overlap between train and test."""
    n = 100
    index = pd.date_range("2020-01-01", periods=n, freq="1h")
    train_bars, test_bars, step_bars = 20, 10, 10
    folds = walk_forward_splits(index, train_bars, test_bars, step_bars, expanding=False)
    assert len(folds) >= 1
    for train_idx, test_idx in folds:
        assert len(train_idx) == train_bars
        assert len(test_idx) == test_bars
        assert train_idx.max() < test_idx.min()


def test_walk_forward_splits_expanding():
    """Expanding: train grows; test follows train."""
    n = 80
    index = pd.date_range("2020-01-01", periods=n, freq="1h")
    train_bars, test_bars, step_bars = 20, 10, 10
    folds = walk_forward_splits(index, train_bars, test_bars, step_bars, expanding=True)
    assert len(folds) >= 1
    for i, (train_idx, test_idx) in enumerate(folds):
        assert len(test_idx) == test_bars
        assert train_idx.min() == index[0]
        if i > 0:
            assert len(train_idx) >= len(folds[i - 1][0])


def test_walk_forward_splits_insufficient_data():
    """Too few points returns empty list."""
    index = pd.DatetimeIndex(["2020-01-01", "2020-01-02"])
    folds = walk_forward_splits(index, 10, 5, 5, expanding=False)
    assert folds == []
