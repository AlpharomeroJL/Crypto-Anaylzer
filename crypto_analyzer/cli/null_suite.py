#!/usr/bin/env python3
"""
Null suite CLI: run null 1/2/3 on signal + returns, write IC/Sharpe null distributions and p-values.
Runs quickly on small fixtures for CI. Research-only.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

import numpy as np
import pandas as pd

from crypto_analyzer.null_suite import run_null_suite, write_null_suite_artifacts


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    ap = argparse.ArgumentParser(description="Run null suite (random ranks, permuted signal, block shuffle)")
    ap.add_argument("--out-dir", type=str, default="null_suite_out", help="Output directory for artifacts")
    ap.add_argument("--n-sim", type=int, default=50, help="Number of null simulations per type (small for CI)")
    ap.add_argument("--block-size", type=int, default=5, help="Block size for null 3")
    ap.add_argument("--seed", type=int, default=42, help="RNG seed")
    ap.add_argument("--freq", type=str, default="1h", help="Frequency label for Sharpe annualization")
    ap.add_argument("--n-ts", type=int, default=30, help="Fixture: number of timestamps (small for CI)")
    ap.add_argument("--n-assets", type=int, default=8, help="Fixture: number of assets")
    args = ap.parse_args(argv)

    # Small fixture: random signal and returns (no structure -> null-like)
    rng = np.random.default_rng(args.seed)
    idx = pd.date_range("2025-01-01", periods=args.n_ts, freq="h")
    cols = [f"A{i}" for i in range(args.n_assets)]
    signal_df = pd.DataFrame(rng.standard_normal((args.n_ts, args.n_assets)), index=idx, columns=cols)
    returns_df = pd.DataFrame(rng.standard_normal((args.n_ts, args.n_assets)) * 0.01, index=idx, columns=cols)

    result = run_null_suite(
        signal_df,
        returns_df,
        n_sim=args.n_sim,
        block_size=args.block_size,
        seed=args.seed,
        freq=args.freq,
    )
    paths = write_null_suite_artifacts(result, args.out_dir)
    print(f"Null suite wrote {len(paths)} artifacts to {args.out_dir}: {paths}")
    print(f"Observed mean_ic={result.observed_mean_ic:.6f} sharpe={result.observed_sharpe:.6f}")
    print(f"p_value_ic: {result.p_value_ic}")
    print(f"p_value_sharpe: {result.p_value_sharpe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
