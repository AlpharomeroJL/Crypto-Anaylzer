"""Purged splits: no overlap between train and test; embargo respected."""

import numpy as np

from crypto_analyzer.folds import FoldSpec, purged_walk_forward_splits


def test_no_overlap_train_test():
    spec = FoldSpec(horizon=5, embargo=2, min_train=10, step=3)
    index = np.arange(50)
    splits = purged_walk_forward_splits(index, spec)
    for train_idx, test_idx in splits:
        train_set = set(train_idx.tolist())
        test_set = set(test_idx.tolist())
        assert train_set.isdisjoint(test_set), "train and test must not overlap"


def test_embargo_respected():
    spec = FoldSpec(horizon=5, embargo=3, min_train=10, step=5)
    index = np.arange(60)
    splits = purged_walk_forward_splits(index, spec)
    for train_idx, test_idx in splits:
        train_max = int(train_idx.max())
        test_min = int(test_idx.min())
        assert test_min >= train_max + spec.embargo, "embargo gap between train end and test start"


def test_splits_shape():
    spec = FoldSpec(horizon=4, embargo=2, min_train=8, step=2)
    splits = purged_walk_forward_splits(np.arange(40), spec)
    assert len(splits) >= 1
    for train_idx, test_idx in splits:
        assert len(train_idx) == spec.min_train or len(train_idx) >= spec.min_train
        assert len(test_idx) == spec.horizon
