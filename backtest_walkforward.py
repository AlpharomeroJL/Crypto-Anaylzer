#!/usr/bin/env python3
"""
Walk-forward backtest CLI. Converts train_days/test_days/step_days to bars and runs OOS folds.
"""
from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import argparse
import numpy as np

from config import db_path, default_freq, min_bars as config_min_bars
from data import load_bars
from crypto_analyzer.walkforward import bars_per_day, run_walkforward_backtest


def main() -> int:
    ap = argparse.ArgumentParser(description="Walk-forward backtest")
    ap.add_argument("--strategy", choices=["trend", "volatility_breakout"], default="trend")
    ap.add_argument("--freq", default=None)
    ap.add_argument("--train-days", type=float, default=30, help="Train window in days")
    ap.add_argument("--test-days", type=float, default=7, help="Test window in days")
    ap.add_argument("--step-days", type=float, default=7, help="Step between folds in days")
    ap.add_argument("--expanding", action="store_true", help="Expanding train window")
    ap.add_argument("--fee-bps", type=float, default=30)
    ap.add_argument("--slippage-bps", type=float, default=10)
    ap.add_argument("--max-pos-liq-pct", type=float, default=None, help="Capacity: max position as pct of liquidity (optional)")
    ap.add_argument("--plot", default=None, metavar="DIR", help="Save equity/drawdown plots to DIR")
    ap.add_argument("--csv", default=None, metavar="FILE", help="Save fold metrics CSV")
    ap.add_argument("--db", default=None)
    args = ap.parse_args()

    freq = args.freq or default_freq() if callable(default_freq) else "1h"
    db = args.db or (db_path() if callable(db_path) else db_path())
    min_bars_count = config_min_bars() if callable(config_min_bars) else 48

    try:
        bars = load_bars(freq, db_path_override=db, min_bars=min_bars_count)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1
    if bars.empty:
        print("No bars.", file=sys.stderr)
        return 1

    bpd = bars_per_day(freq)
    train_bars = max(1, int(args.train_days * bpd))
    test_bars = max(1, int(args.test_days * bpd))
    step_bars = max(1, int(args.step_days * bpd))

    costs = {"fee_bps": args.fee_bps, "slippage_bps": args.slippage_bps}
    params = {}
    if args.max_pos_liq_pct is not None:
        params["max_pos_liq_pct"] = args.max_pos_liq_pct

    stitched, fold_df, fold_metrics = run_walkforward_backtest(
        bars, freq, args.strategy,
        train_bars=train_bars,
        test_bars=test_bars,
        step_bars=step_bars,
        params=params,
        costs=costs,
        expanding=args.expanding,
    )

    if not fold_metrics:
        print("No folds (not enough data).")
        return 0

    print("Fold metrics:")
    print(fold_df.to_string(index=False))

    if stitched is not None and not stitched.empty:
        total_return = float(stitched.iloc[-1] / stitched.iloc[0] - 1.0)
        print(f"\nStitched equity total return: {total_return:.4f}")

    if args.csv and not fold_df.empty:
        args.csv = Path(args.csv)
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        fold_df.to_csv(args.csv, index=False)
        print(f"Wrote {args.csv}")

    if args.plot and stitched is not None and not stitched.empty:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            args.plot = Path(args.plot)
            args.plot.mkdir(parents=True, exist_ok=True)
            fig, ax = plt.subplots(1, 1)
            stitched.plot(ax=ax)
            ax.set_title(f"Walk-forward equity — {args.strategy} ({freq})")
            ax.set_ylabel("Equity")
            plt.tight_layout()
            plt.savefig(args.plot / "equity.png", dpi=150)
            plt.close()
            fig, ax = plt.subplots(1, 1)
            dd = stitched.cummax() - stitched
            dd.plot(ax=ax)
            ax.set_title(f"Drawdown — {args.strategy} ({freq})")
            plt.tight_layout()
            plt.savefig(args.plot / "drawdown.png", dpi=150)
            plt.close()
            print(f"Plots saved to {args.plot}")
        except Exception as e:
            print(f"Plot failed: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
