#!/usr/bin/env python3
"""
Backtest on bars_{freq}. Strategies: trend (EMA20 > EMA50 + vol filter), volatility_breakout (z-score + trailing stop).
Fees (bps), slippage proxy from liquidity, fixed-fraction position sizing.
Output: equity curve, drawdown plot, trades CSV, summary table.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

# Backtest logic lives in library; CLI is thin wrapper
from crypto_analyzer.backtest_core import (
    DEFAULT_FEE_BPS,
    metrics,
    run_trend_strategy,
    run_vol_breakout_strategy,
)
from crypto_analyzer.config import db_path, default_freq
from crypto_analyzer.config import min_bars as config_min_bars
from crypto_analyzer.data import load_bars


def main() -> int:
    ap = argparse.ArgumentParser(description="Backtest on bars")
    ap.add_argument("--strategy", choices=["trend", "volatility_breakout"], default="trend")
    ap.add_argument("--db", default=None)
    ap.add_argument("--freq", default=None)
    ap.add_argument("--fee-bps", type=float, default=DEFAULT_FEE_BPS)
    ap.add_argument(
        "--slippage-bps", type=float, default=None, help="Fixed slippage bps per trade (default: liquidity-based proxy)"
    )
    ap.add_argument("--position-pct", type=float, default=0.25)
    ap.add_argument("--csv", default=None, metavar="FILE", help="Trades CSV path")
    ap.add_argument("--plot", default=None, metavar="DIR", help="Save equity and drawdown plots to DIR")
    args = ap.parse_args()

    db = args.db or (db_path() if callable(db_path) else db_path())
    freq = args.freq or (default_freq() if callable(default_freq) else "1h")
    min_bars_count = config_min_bars() if callable(config_min_bars) else 48

    try:
        bars = load_bars(freq, db_path_override=db, min_bars=min_bars_count)
    except FileNotFoundError as e:
        print(e)
        print("Run: python materialize_bars.py --freq", freq)
        return 1

    if bars.empty:
        print("No bars. Run materialize_bars.py first.")
        return 1

    # Gross (no costs) and net (with costs)
    if args.strategy == "trend":
        _, equity_gross = run_trend_strategy(
            bars, freq, fee_bps=0, position_pct=args.position_pct, slippage_bps_fixed=0
        )
        trades_df, equity = run_trend_strategy(
            bars, freq, fee_bps=args.fee_bps, position_pct=args.position_pct, slippage_bps_fixed=args.slippage_bps
        )
    else:
        _, equity_gross = run_vol_breakout_strategy(
            bars, freq, fee_bps=0, position_pct=args.position_pct, slippage_bps_fixed=0
        )
        trades_df, equity = run_vol_breakout_strategy(
            bars, freq, fee_bps=args.fee_bps, position_pct=args.position_pct, slippage_bps_fixed=args.slippage_bps
        )

    if equity.empty:
        print("No equity series (not enough data for strategy).")
        return 1

    met = metrics(equity, freq)
    met["n_trades"] = len(trades_df) if trades_df is not None and not trades_df.empty else 0
    if not equity_gross.empty and len(equity_gross) >= 2:
        gross_return = float(equity_gross.iloc[-1] / equity_gross.iloc[0] - 1.0)
        met["gross_total_return"] = gross_return
        met["net_total_return"] = met["total_return"]
        met["cost_drag_pct"] = (gross_return - met["total_return"]) * 100.0
    else:
        met["gross_total_return"] = met["total_return"]
        met["net_total_return"] = met["total_return"]
        met["cost_drag_pct"] = 0.0
    print("Backtest summary")
    print("-" * 40)
    for k, v in met.items():
        if isinstance(v, float) and not np.isnan(v):
            print(f"  {k}: {v:.4f}")
        else:
            print(f"  {k}: {v}")

    if not trades_df.empty and args.csv:
        Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
        trades_df.to_csv(args.csv, index=False)
        print(f"Trades written to {args.csv}")

    if args.plot:
        import matplotlib.pyplot as plt

        Path(args.plot).mkdir(parents=True, exist_ok=True)
        fig, ax = plt.subplots(1, 1)
        equity.plot(ax=ax)
        ax.set_title(f"Equity curve — {args.strategy} ({freq})")
        ax.set_ylabel("Equity")
        plt.tight_layout()
        plt.savefig(Path(args.plot) / "equity.png", dpi=150)
        plt.close()
        fig, ax = plt.subplots(1, 1)
        dd = equity.cummax() - equity
        dd.plot(ax=ax)
        ax.set_title(f"Drawdown — {args.strategy} ({freq})")
        ax.set_ylabel("Drawdown")
        plt.tight_layout()
        plt.savefig(Path(args.plot) / "drawdown.png", dpi=150)
        plt.close()
        print(f"Plots saved to {args.plot}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
