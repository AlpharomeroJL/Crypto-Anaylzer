"""
Walk-forward / out-of-sample validation. No lookahead; fit only on train, simulate on test.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def bars_per_day(freq: str) -> float:
    """Bars per calendar day for given freq."""
    from .features import bars_per_day as _bpd
    return _bpd(freq)


def walk_forward_splits(
    index: pd.DatetimeIndex,
    train_bars: int,
    test_bars: int,
    step_bars: int,
    expanding: bool = False,
) -> List[Tuple[pd.DatetimeIndex, pd.DatetimeIndex]]:
    """
    Yield (train_index, test_index) for each fold. No overlap between train and test.
    - expanding: train grows by step_bars each fold (start stays 0).
    - rolling: train slides by step_bars each time.
    index: sorted unique timestamps (e.g. bars_df["ts_utc"].drop_duplicates().sort_values()).
    """
    idx = index.sort_values().drop_duplicates()
    if hasattr(idx, "values"):
        times = idx.values
    else:
        times = np.asarray(idx)
    n = len(times)
    if n < train_bars + test_bars or train_bars <= 0 or test_bars <= 0 or step_bars <= 0:
        return []

    out = []
    if expanding:
        train_end = train_bars
        while train_end + test_bars <= n:
            test_start = train_end
            test_end = test_start + test_bars
            train_idx = pd.DatetimeIndex(times[0:train_end])
            test_idx = pd.DatetimeIndex(times[test_start:test_end])
            out.append((train_idx, test_idx))
            train_end += step_bars
    else:
        start = 0
        while start + train_bars + test_bars <= n:
            train_end = start + train_bars
            test_start = train_end
            test_end = test_start + test_bars
            train_idx = pd.DatetimeIndex(times[start:train_end])
            test_idx = pd.DatetimeIndex(times[test_start:test_end])
            out.append((train_idx, test_idx))
            start += step_bars
    return out


def run_walkforward_backtest(
    bars_df: pd.DataFrame,
    freq: str,
    strategy: str,
    train_bars: int,
    test_bars: int,
    step_bars: int,
    params: Optional[Dict[str, Any]] = None,
    costs: Optional[Dict[str, float]] = None,
    expanding: bool = False,
) -> Tuple[pd.Series, pd.DataFrame, List[Dict]]:
    """
    Run backtest on each fold (train then test). Strategy state is fit only on train;
    for trend/vol_breakout we just compute indicators on train and simulate on test using test data only.
    Returns: (stitched_equity_series, per_fold_metrics_list).
    stitched_equity: concatenated equity from each test fold (no overlap).
    """
    import sys
    from pathlib import Path
    _root = Path(__file__).resolve().parent.parent
    _cli = _root / "cli"
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
    if str(_cli) not in sys.path:
        sys.path.insert(0, str(_cli))
    from backtest import run_trend_strategy, run_vol_breakout_strategy, metrics as backtest_metrics

    params = params or {}
    costs = costs or {}
    fee_bps = costs.get("fee_bps", 30.0)
    position_pct = params.get("position_pct", 0.25)

    bars_df = bars_df.sort_values(["chain_id", "pair_address", "ts_utc"])
    global_index = bars_df["ts_utc"].drop_duplicates().sort_values().reset_index(drop=True)
    folds = walk_forward_splits(global_index, train_bars, test_bars, step_bars, expanding=expanding)
    if not folds:
        return pd.Series(dtype=float), pd.DataFrame(), []

    all_equity = []
    fold_metrics = []

    for fold_idx, (train_idx, test_idx) in enumerate(folds):
        train_ts = train_idx
        test_ts = test_idx
        train_bars_sub = bars_df[bars_df["ts_utc"].isin(train_ts)]
        test_bars_sub = bars_df[bars_df["ts_utc"].isin(test_ts)]
        if test_bars_sub.empty:
            continue
        if strategy == "trend":
            trades_df, equity = run_trend_strategy(
                test_bars_sub, freq, fee_bps=fee_bps, position_pct=position_pct, **{k: v for k, v in params.items() if k not in ("position_pct",)}
            )
        else:
            trades_df, equity = run_vol_breakout_strategy(
                test_bars_sub, freq, fee_bps=fee_bps, position_pct=position_pct, **{k: v for k, v in params.items() if k not in ("position_pct",)}
            )
        if equity is None or (hasattr(equity, "empty") and equity.empty):
            continue
        all_equity.append(equity)
        met = backtest_metrics(equity, freq)
        met["fold"] = fold_idx
        met["train_start"] = train_ts.min() if hasattr(train_ts, "min") else train_ts[0]
        met["train_end"] = train_ts.max() if hasattr(train_ts, "max") else train_ts[-1]
        met["test_start"] = test_ts.min() if hasattr(test_ts, "min") else test_ts[0]
        met["test_end"] = test_ts.max() if hasattr(test_ts, "max") else test_ts[-1]
        fold_metrics.append(met)

    if not all_equity:
        return pd.Series(dtype=float), pd.DataFrame(), fold_metrics
    stitched = pd.concat(all_equity, axis=0)
    stitched = stitched[~stitched.index.duplicated(keep="first")].sort_index()
    fold_df = pd.DataFrame(fold_metrics)
    return stitched, fold_df, fold_metrics
