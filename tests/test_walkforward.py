"""Walk-forward backtest: stitched OOS index, import without path hacks."""

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from crypto_analyzer.walkforward import run_walkforward_backtest, walk_forward_splits


def test_stitched_oos_index_unique_and_sorted():
    """Stitched OOS equity series has unique index and is sorted."""
    # Trend strategy needs >= ema_slow+5 (55) bars per pair per fold
    n = 200
    index = pd.date_range("2020-01-01", periods=n, freq="1h")
    bars_df = pd.DataFrame(
        {
            "ts_utc": index,
            "chain_id": 1,
            "pair_address": "0xabc",
            "close": 100.0,
            "liquidity_usd": 1e6,
        }
    )
    stitched, fold_df, fold_metrics = run_walkforward_backtest(
        bars_df,
        "1h",
        "trend",
        train_bars=60,
        test_bars=60,
        step_bars=60,
        expanding=False,
    )
    if stitched.empty:
        pytest.skip("No folds produced (need enough data)")
    assert stitched.index.is_unique, "stitched OOS index must be unique"
    assert stitched.index.is_monotonic_increasing, "stitched OOS index must be sorted"


def test_walkforward_import_from_any_cwd():
    """run_walkforward_backtest is importable without repo-root or sys.path hacks."""
    # Run from a different cwd to ensure package resolution, not cwd
    result = subprocess.run(
        [sys.executable, "-c", "from crypto_analyzer.walkforward import run_walkforward_backtest; print('ok')"],
        cwd=Path(__file__).resolve().parent,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")
    assert "ok" in (result.stdout or "")


def test_splits_non_overlapping_train_test():
    """Across all folds, train and test indices never overlap within a fold."""
    n = 100
    index = pd.date_range("2020-01-01", periods=n, freq="1h")
    folds = walk_forward_splits(index, train_bars=20, test_bars=10, step_bars=10, expanding=False)
    for train_idx, test_idx in folds:
        train_set = set(train_idx)
        test_set = set(test_idx)
        assert train_set.isdisjoint(test_set), "train and test must be disjoint"
