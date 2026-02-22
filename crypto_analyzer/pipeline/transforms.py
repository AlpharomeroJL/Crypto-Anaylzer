"""
Transform base class: fit on train only, transform applied to data.
exogenous: if True, transform does not use target/label (no leakage).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

import numpy as np
import pandas as pd

T = TypeVar("T", np.ndarray, pd.DataFrame, pd.Series)


class Transform(ABC, Generic[T]):
    """Base transform: fit(train) -> self; transform(x) -> x2. Fit must be called only on train."""

    exogenous: bool = True  # True => no target used, safe for causal folds

    @abstractmethod
    def fit(self, train: T) -> "Transform[T]":
        """Fit on train data only. Returns self."""
        ...

    @abstractmethod
    def transform(self, x: T) -> T:
        """Transform data (train or test)."""
        ...


class NoOpTransform(Transform[T]):
    """No-op transform for testing: fit does nothing, transform returns input."""

    exogenous = True

    def fit(self, train: T) -> "NoOpTransform[T]":
        return self

    def transform(self, x: T) -> T:
        return x
