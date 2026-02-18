#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sqlite3

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

DB_PATH = "dex_data.sqlite"
OUT_DIR = "plots"
SHOW_PLOTS = False  # set True or use --show to display plot windows after saving

# matches your poller table
TABLE = "sol_monitor_snapshots"
SPOT_TABLE = "spot_price_snapshots"

# Set True once you have at least a day of data for meaningful daily returns/vol
DAILY_MODE = False

# Defaults (can be overridden via CLI)
DEFAULT_MIN_POINTS_FOR_RATIOS = 300  # ~5 hours @ 1-min bars in minute-mode

if DAILY_MODE:
    RESAMPLE_FREQ = "1D"
    ROLLING_WINDOW = 7
    PERIODS_PER_YEAR = 365.0
    DEFAULT_MIN_POINTS_FOR_RATIOS = 30  # ~1 month of days
else:
    # Even if you poll faster (e.g., every 10s), analyze at 1-minute closes to reduce noise.
    RESAMPLE_FREQ = "1min"
    ROLLING_WINDOW = 30               # 30 minutes
    PERIODS_PER_YEAR = 365 * 24 * 60  # minutes/year
    DEFAULT_MIN_POINTS_FOR_RATIOS = 300


def sharpe_ratio(r: pd.Series, periods_per_year: float) -> float:
    r = r.dropna()
    if r.empty:
        return float("nan")
    s = r.std(ddof=1)
    if s == 0 or np.isnan(s):
        return float("nan")
    return float((r.mean() / s) * np.sqrt(periods_per_year))


def sortino_ratio(r: pd.Series, periods_per_year: float) -> float:
    r = r.dropna()
    if r.empty:
        return float("nan")
    downside = r.clip(upper=0)
    dd = np.sqrt((downside**2).mean())
    if dd == 0 or np.isnan(dd):
        return float("nan")
    return float((r.mean() / dd) * np.sqrt(periods_per_year))


def savefig_and_maybe_show(path: str, show: bool) -> None:
    """Save figure to path. If show=False, close figure immediately."""
    plt.savefig(path, dpi=150)
    if not show:
        plt.close()


def main() -> int:
    global SHOW_PLOTS
    parser = argparse.ArgumentParser(description="Analyze DEX + spot data from SQLite and save plots.")
    parser.add_argument("--show", action="store_true", help="Display plot windows after saving (default: only save to files)")
    parser.add_argument(
        "--min_ratio_points",
        type=int,
        default=DEFAULT_MIN_POINTS_FOR_RATIOS,
        help="Min resampled points required before printing Sharpe/Sortino (default based on DAILY_MODE)",
    )
    args = parser.parse_args()

    if args.show:
        SHOW_PLOTS = True

    min_points_for_ratios = args.min_ratio_points

    print("Analyzer starting...")
    os.makedirs(OUT_DIR, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    try:
        tables = conn.execute("select name from sqlite_master where type='table'").fetchall()
        print("Tables:", tables)
        if (TABLE,) not in tables:
            raise SystemExit(f"Table '{TABLE}' not found.")

        # Dex metrics (always from sol_monitor for liquidity/vol overlay)
        dex_df = pd.read_sql_query(
            f"""
            SELECT ts_utc, spot_price_usd, liquidity_usd, vol_h24,
                   txns_h24_buys, txns_h24_sells
            FROM {TABLE}
            ORDER BY ts_utc ASC
            """,
            conn,
        )

        # Multi-asset: load from spot_price_snapshots if available
        spot_df = None
        if (SPOT_TABLE,) in tables:
            spot_df = pd.read_sql_query(
                f"""
                SELECT ts_utc, symbol, spot_price_usd
                FROM {SPOT_TABLE}
                ORDER BY ts_utc ASC
                """,
                conn,
            )
    finally:
        conn.close()

    print("Loaded rows (dex):", len(dex_df))
    if dex_df.empty:
        raise SystemExit("No rows yet — let the poller run longer.")

    dex_df["ts_utc"] = pd.to_datetime(dex_df["ts_utc"], utc=True)
    dex_df = dex_df.set_index("ts_utc")

    multi_asset = False
    prices_by_symbol: dict[str, pd.Series] = {}

    if spot_df is not None and not spot_df.empty:
        symbols = spot_df["symbol"].unique().tolist()
        if len(symbols) >= 2:
            multi_asset = True
            print("Multi-asset mode: symbols", symbols)
            for sym in symbols:
                sub = spot_df[spot_df["symbol"] == sym][["ts_utc", "spot_price_usd"]].copy()
                sub["ts_utc"] = pd.to_datetime(sub["ts_utc"], utc=True)
                sub = sub.set_index("ts_utc").sort_index()
                pr = sub["spot_price_usd"].astype(float).resample(RESAMPLE_FREQ).last().dropna()
                if len(pr) >= 2:
                    prices_by_symbol[sym] = pr
        else:
            print("Single symbol in spot table; using dex table for SOL.")

    prices_multi: pd.DataFrame | None = None

    if not multi_asset or not prices_by_symbol:
        # Single-asset: use dex table SOL spot price
        price = dex_df["spot_price_usd"].astype(float).resample(RESAMPLE_FREQ).last().dropna()
        prices_by_symbol = {"SOL": price}
    else:
        # Inner join: only timestamps where every asset has a value (no comparing non-overlapping periods)
        prices_multi = pd.DataFrame(prices_by_symbol).dropna(how="any")
        if prices_multi.empty or len(prices_multi) < 2:
            multi_asset = False
            price = dex_df["spot_price_usd"].astype(float).resample(RESAMPLE_FREQ).last().dropna()
            prices_by_symbol = {"SOL": price}
            prices_multi = None
        else:
            price = prices_multi["SOL"] if "SOL" in prices_multi else prices_multi.iloc[:, 0]

    liq = dex_df["liquidity_usd"].astype(float).resample(RESAMPLE_FREQ).last()
    vol24 = dex_df["vol_h24"].astype(float).resample(RESAMPLE_FREQ).last()

    print("Resampled points (SOL series):", len(price))

    if len(price) < 3:
        print("Not enough points for returns/vol yet. Saved price plot only.")
        plt.figure()
        price.plot()
        plt.title("SOL Spot Price (USD)")
        plt.xlabel("Time (UTC)")
        plt.ylabel("USD")
        plt.tight_layout()
        outp = os.path.join(OUT_DIR, "sol_spot_price.png")
        savefig_and_maybe_show(outp, SHOW_PLOTS)
        print("Saved:", outp)
        if SHOW_PLOTS:
            plt.show()
        return 0

    # Returns (SOL)
    r_arith = price.pct_change()
    cum_return = (1.0 + r_arith.fillna(0)).cumprod() - 1.0

    # Rolling volatility (SOL)
    roll_vol = r_arith.rolling(ROLLING_WINDOW).std(ddof=1)
    roll_vol_ann = roll_vol * np.sqrt(PERIODS_PER_YEAR)

    n_pts = len(price)
    if n_pts >= min_points_for_ratios:
        sh = sharpe_ratio(r_arith, PERIODS_PER_YEAR)
        so = sortino_ratio(r_arith, PERIODS_PER_YEAR)
        print(f"Sharpe (rf=0):  {sh:.3f}")
        print(f"Sortino (rf=0): {so:.3f}")

        if prices_multi is not None:
            for sym in prices_multi.columns:
                r = prices_multi[sym].pct_change()
                print(f"  {sym}: Sharpe={sharpe_ratio(r, PERIODS_PER_YEAR):.3f}  Sortino={sortino_ratio(r, PERIODS_PER_YEAR):.3f}")
    else:
        print(f"Need {min_points_for_ratios}+ resampled points for Sharpe/Sortino (have {n_pts}). Plots only.")

    # ---- PLOTS ----
    saved: list[str] = []

    # 1) SOL Price
    plt.figure()
    price.plot()
    plt.title("SOL Spot Price (USD)")
    plt.xlabel("Time (UTC)")
    plt.ylabel("USD")
    plt.tight_layout()
    p1 = os.path.join(OUT_DIR, "sol_price.png")
    savefig_and_maybe_show(p1, SHOW_PLOTS)
    saved.append(p1)

    # 2) SOL Cumulative return
    plt.figure()
    cum_return.plot()
    plt.title("SOL Cumulative Return")
    plt.xlabel("Time (UTC)")
    plt.ylabel("Cumulative Return")
    plt.tight_layout()
    p2 = os.path.join(OUT_DIR, "sol_cum_return.png")
    savefig_and_maybe_show(p2, SHOW_PLOTS)
    saved.append(p2)

    # 3) SOL return histogram
    plt.figure()
    r_arith.dropna().hist(bins=50)
    plt.title("SOL Return Histogram (Arithmetic)")
    plt.xlabel("Return")
    plt.ylabel("Frequency")
    plt.tight_layout()
    p3 = os.path.join(OUT_DIR, "sol_return_hist.png")
    savefig_and_maybe_show(p3, SHOW_PLOTS)
    saved.append(p3)

    # 4) SOL rolling vol (annualized)
    plt.figure()
    roll_vol_ann.plot()
    window_label = f"{ROLLING_WINDOW} days" if DAILY_MODE else f"{ROLLING_WINDOW} bars"
    plt.title(f"SOL Rolling Volatility (annualized, window={window_label})")
    plt.xlabel("Time (UTC)")
    plt.ylabel("Annualized Volatility")
    plt.tight_layout()
    p4 = os.path.join(OUT_DIR, "sol_rolling_vol.png")
    savefig_and_maybe_show(p4, SHOW_PLOTS)
    saved.append(p4)

    # 5) Volatility clustering: |returns| + rolling std (NOT annualized)
    plt.figure()
    r_arith.abs().plot(alpha=0.65, label="|return|")
    roll_vol.plot(label="rolling std")
    plt.legend()
    plt.title("Volatility clustering: |returns| and rolling volatility")
    plt.xlabel("Time (UTC)")
    plt.tight_layout()
    p_cluster = os.path.join(OUT_DIR, "sol_vol_clusters.png")
    savefig_and_maybe_show(p_cluster, SHOW_PLOTS)
    saved.append(p_cluster)

    # 6) Dex liquidity
    plt.figure()
    liq.plot()
    plt.title("Dex Liquidity (USD) — SOL/USDC pool")
    plt.xlabel("Time (UTC)")
    plt.ylabel("Liquidity USD")
    plt.tight_layout()
    p5 = os.path.join(OUT_DIR, "dex_liquidity.png")
    savefig_and_maybe_show(p5, SHOW_PLOTS)
    saved.append(p5)

    # 7–10) Multi-asset comparison (if we have SOL, ETH, BTC)
    if prices_multi is not None and len(prices_multi.columns) >= 2:
        print("Saving multi-asset comparison plots (normalized price, cum return, rolling vol, correlation)...")

        # Normalized price (base 100 at start)
        norm = (prices_multi / prices_multi.iloc[0]) * 100
        plt.figure()
        for col in norm.columns:
            norm[col].plot(label=col)
        plt.legend()
        plt.title("Spot price (normalized to 100)")
        plt.xlabel("Time (UTC)")
        plt.ylabel("Index")
        plt.tight_layout()
        p6 = os.path.join(OUT_DIR, "multi_asset_normalized.png")
        savefig_and_maybe_show(p6, SHOW_PLOTS)
        saved.append(p6)

        # Cumulative return by asset
        cum = (1.0 + prices_multi.pct_change().fillna(0)).cumprod() - 1.0
        plt.figure()
        for col in cum.columns:
            cum[col].plot(label=col)
        plt.legend()
        plt.title("Cumulative return (all assets)")
        plt.xlabel("Time (UTC)")
        plt.ylabel("Cumulative Return")
        plt.tight_layout()
        p7 = os.path.join(OUT_DIR, "multi_asset_cum_return.png")
        savefig_and_maybe_show(p7, SHOW_PLOTS)
        saved.append(p7)

        # Rolling volatility comparison (annualized)
        rets_multi = prices_multi.pct_change()
        roll_vol_multi = rets_multi.rolling(ROLLING_WINDOW).std(ddof=1) * np.sqrt(PERIODS_PER_YEAR)
        plt.figure()
        for col in roll_vol_multi.columns:
            roll_vol_multi[col].plot(label=col)
        plt.legend()
        plt.title(f"Rolling Volatility (annualized, window={window_label})")
        plt.xlabel("Time (UTC)")
        plt.ylabel("Annualized Volatility")
        plt.tight_layout()
        p8 = os.path.join(OUT_DIR, "multi_asset_rolling_vol.png")
        savefig_and_maybe_show(p8, SHOW_PLOTS)
        saved.append(p8)

        # Correlation matrix of returns
        corr = rets_multi.dropna().corr()
        corr_csv = os.path.join(OUT_DIR, "multi_asset_corr.csv")
        corr.to_csv(corr_csv)
        print("Saved correlation CSV:", corr_csv)

        plt.figure()
        plt.imshow(corr.values, interpolation="nearest", vmin=-1, vmax=1, cmap="RdBu_r")
        plt.xticks(range(len(corr.columns)), corr.columns)
        plt.yticks(range(len(corr.index)), corr.index)
        plt.colorbar(label="Correlation")
        plt.title("Return Correlation Matrix")
        plt.tight_layout()
        p9 = os.path.join(OUT_DIR, "multi_asset_corr.png")
        savefig_and_maybe_show(p9, SHOW_PLOTS)
        saved.append(p9)

    print("Saved plots:")
    for p in saved:
        print(" ", p)

    if SHOW_PLOTS:
        plt.show()  # open all plot windows at once (block until you close them)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
