"""Cumulative return from log returns; drawdown correctness."""
import numpy as np
import pandas as pd
import pytest
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.features import (
    log_returns,
    cumulative_returns_log,
    compute_drawdown_from_log_returns,
    compute_drawdown_from_equity,
)


def test_cumulative_return_from_log_returns():
    """exp(cumsum(log_ret)) - 1 matches simple return product."""
    np.random.seed(42)
    n = 50
    simple_ret = np.random.randn(n) * 0.01
    close = np.exp(np.cumsum(np.log(1 + simple_ret)))
    close_ser = pd.Series(close)
    lr = log_returns(close_ser)
    cum = cumulative_returns_log(lr)
    expected = close[-1] / close[0] - 1.0
    assert abs(cum.iloc[-1] - expected) < 1e-10


def test_drawdown_correctness():
    """Drawdown = equity/peak - 1 (non-positive when below peak); max_dd is min (most negative)."""
    np.random.seed(42)
    equity = pd.Series(np.exp(np.cumsum(np.random.randn(100) * 0.02)))
    dd_ser, max_dd = compute_drawdown_from_equity(equity)
    assert (dd_ser <= 0).all()
    assert max_dd <= 0
    assert dd_ser.min() == max_dd
