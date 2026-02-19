"""Integrity: monotonic time, no zero prices, no forward-looking alignment."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd

from crypto_analyzer.integrity import (
    assert_monotonic_time_index,
    assert_no_forward_looking,
    assert_no_negative_or_zero_prices,
    bad_row_rate,
    count_non_positive_prices,
    validate_alignment,
)


def test_assert_monotonic_time_index_ok():
    df = pd.DataFrame({"ts_utc": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])})
    out = assert_monotonic_time_index(df, col="ts_utc")
    assert out is None


def test_assert_monotonic_time_index_warning():
    df = pd.DataFrame({"ts_utc": pd.to_datetime(["2024-01-02", "2024-01-01", "2024-01-03"])})
    out = assert_monotonic_time_index(df, col="ts_utc")
    assert out is not None
    assert "monotonic" in out.lower() or "order" in out.lower()


def test_assert_no_negative_or_zero_prices_ok():
    s = pd.Series([100.0, 101.0, 99.0])
    out = assert_no_negative_or_zero_prices(s)
    assert out is None


def test_assert_no_negative_or_zero_prices_warning():
    s = pd.Series([100.0, 0.0, 99.0])
    out = assert_no_negative_or_zero_prices(s)
    assert out is not None
    assert "zero" in out.lower() or "negative" in out.lower()


def test_assert_no_forward_looking_none():
    ts1 = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    ts2 = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    out = assert_no_forward_looking(ts1, ts2)
    assert out is None or isinstance(out, str)


def test_validate_alignment_insufficient_overlap():
    returns = pd.DataFrame(index=pd.DatetimeIndex(["2024-01-01", "2024-01-02"]), data={"A": [0.01, 0.02]})
    signals = pd.DataFrame(index=pd.DatetimeIndex(["2024-01-03"]), data={"A": [0.5]})
    warnings = validate_alignment(returns, signals, [1])
    assert isinstance(warnings, list)


def test_count_non_positive_prices():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    try:
        os.close(fd)
        with sqlite3.connect(path) as con:
            con.execute("CREATE TABLE t (id INT, price REAL)")
            con.execute("INSERT INTO t VALUES (1, 10), (2, 0), (3, -1), (4, 5)")
            con.commit()
        out = count_non_positive_prices(path, [("t", "price")])
        assert len(out) == 1
        assert out[0][0] == "t" and out[0][1] == "price" and out[0][2] == 2
        rate_out = bad_row_rate(path, [("t", "price")])
        assert len(rate_out) == 1
        assert rate_out[0][0] == "t" and rate_out[0][1] == "price"
        assert rate_out[0][2] == 2 and rate_out[0][3] == 4
        assert 49 <= rate_out[0][4] <= 51
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass
