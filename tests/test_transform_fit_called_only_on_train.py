"""Transform: fit called only on train (spy harness)."""

import numpy as np

from crypto_analyzer.pipeline.transforms import NoOpTransform, Transform


def test_noop_transform_fit_returns_self():
    t = NoOpTransform()
    out = t.fit(np.array([1.0, 2.0, 3.0]))
    assert out is t


def test_noop_transform_transform_returns_input():
    x = np.array([1.0, 2.0])
    t = NoOpTransform()
    t.fit(x)
    out = t.transform(x)
    np.testing.assert_array_equal(out, x)


def test_fit_called_only_on_train_harness():
    """Small harness: simulate fold loop; fit only on train indices, transform on test."""
    train_idx = np.array([0, 1, 2])
    test_idx = np.array([3, 4])
    X = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    fit_called_with: list[np.ndarray] = []

    class SpyTransform(Transform[np.ndarray]):
        exogenous = True

        def fit(self, train: np.ndarray) -> "SpyTransform":
            fit_called_with.append(train.copy())
            return self

        def transform(self, x: np.ndarray) -> np.ndarray:
            return x

    t = SpyTransform()
    train_data = X[train_idx]
    test_data = X[test_idx]
    t.fit(train_data)
    _ = t.transform(test_data)
    assert len(fit_called_with) == 1
    np.testing.assert_array_equal(fit_called_with[0], train_data)
    assert not np.array_equal(fit_called_with[0], test_data)
