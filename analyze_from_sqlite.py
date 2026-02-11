#!/usr/bin/env python3
"""
Step 3: Analyze stored Dexscreener snapshots (SQLite) -> returns/volatility/plots.

Run:
  python analyze_from_sqlite.py

It reads dex_data.sqlite and produces PNG plots in ./plots
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

DB_PATH = "dex_data.sqlite"
OUT_DIR = "plots"

# Select the pair you want to analyze (must match what you stored)
CHAIN_ID = "solana"
PAIR_ADDRESS = "AvSUmeK93LAo2DGZaojQuU3WFCGB895L2CzUgdEewZEX"

# Resampling frequency:
# - "1min" good for your current 60s polling
# - later you can do "5min", "1H", "1D"
RESAMPLE_FREQ = "1min"

# Rolling window size in periods of RESAMPLE_FREQ (e.g., 30 minutes if RESAMPLE_FREQ="1min")
ROLLING_WINDOW = 5

# Annualization assumption:
# If you’re using minute returns, you can annualize with minutes/year.
# For quick prototypes, it’s fine. For “daily” analytics, resample to "1D".
MINUTES_PER_YEAR = 365 * 24 * 60


def load_pair_snapshots(db_path: str, chain_id: str, pair_address: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(
            """
            SELECT ts_utc, chain_id, pair_address,
                   base_symbol, quote_symbol,
                   price_usd, liquidity_usd
            FROM pair_snapshots
            WHERE chain_id = ? AND pair_address = ?
            ORDER BY ts_utc ASC
            """,
            conn,
            params=(chain_id, pair_address),
        )
    finally:
        conn.close()

    if df.empty:
        raise RuntimeError("No rows found for that (chain_id, pair_address).")

    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True)
    df = df.set_index("ts_utc")
    return df


def compute_returns(prices: pd.Series) -> pd.DataFrame:
    prices = prices.astype(float)

    # Arithmetic returns
    r_arith = prices.pct_change()

    # Log returns
    r_log = np.log(prices).diff()

    out = pd.DataFrame({"price": prices, "r_arith": r_arith, "r_log": r_log})
    return out


def sharpe_ratio(returns: pd.Series, periods_per_year: float, rf: float = 0.0) -> float:
    r = returns.dropna()
    if r.empty:
        return float("nan")
    excess = r - (rf / periods_per_year)
    mu = excess.mean()
    sigma = excess.std(ddof=1)
    if sigma == 0 or np.isnan(sigma):
        return float("nan")
    return float((mu / sigma) * np.sqrt(periods_per_year))


def sortino_ratio(returns: pd.Series, periods_per_year: float, rf: float = 0.0) -> float:
    r = returns.dropna()
    if r.empty:
        return float("nan")
    target = rf / periods_per_year
    downside = (r - target).clip(upper=0)
    downside_dev = np.sqrt((downside**2).mean())
    if downside_dev == 0 or np.isnan(downside_dev):
        return float("nan")
    return float(((r.mean() - target) / downside_dev) * np.sqrt(periods_per_year))


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)

    df = load_pair_snapshots(DB_PATH, CHAIN_ID, PAIR_ADDRESS)

    base = df["base_symbol"].dropna().iloc[-1] if df["base_symbol"].notna().any() else "BASE"
    quote = df["quote_symbol"].dropna().iloc[-1] if df["quote_symbol"].notna().any() else "QUOTE"
    label = f"{base}_{quote}_{CHAIN_ID}"

    # Resample to closes (last price in each bucket)
    price = df["price_usd"].resample(RESAMPLE_FREQ).last().dropna()

    # Compute returns
    ret = compute_returns(price)

    # Cumulative return (arith)
    ret["cum_return"] = (1.0 + ret["r_arith"].fillna(0)).cumprod() - 1.0

    # Rolling volatility (use arithmetic returns)
    ret["roll_vol"] = ret["r_arith"].rolling(ROLLING_WINDOW).std(ddof=1)

    # Annualize vol depending on frequency
    freq = pd.tseries.frequencies.to_offset(RESAMPLE_FREQ)
    if freq.name.lower().endswith("min"):
        periods_per_year = MINUTES_PER_YEAR / freq.n
    elif freq.name.lower().endswith("h"):
        periods_per_year = 365 * 24 / freq.n
    elif freq.name.lower().endswith("d"):
        periods_per_year = 365 / freq.n
    else:
        # fallback
        periods_per_year = MINUTES_PER_YEAR

    ann_vol = ret["roll_vol"] * np.sqrt(periods_per_year)
    ret["roll_vol_ann"] = ann_vol

    # Risk metrics (use arithmetic returns)
    sharpe = sharpe_ratio(ret["r_arith"], periods_per_year=periods_per_year, rf=0.0)
    sortino = sortino_ratio(ret["r_arith"], periods_per_year=periods_per_year, rf=0.0)

    print(f"Pair: {base}/{quote} on {CHAIN_ID}")
    print(f"Rows (raw snapshots): {len(df)}")
    print(f"Rows (resampled {RESAMPLE_FREQ}): {len(ret.dropna(subset=['price']))}")
    print(f"Sharpe (rf=0):  {sharpe:.3f}")
    print(f"Sortino (rf=0): {sortino:.3f}")

    # ---- PLOTS ----
    # 1) Price
    plt.figure()
    ret["price"].plot()
    plt.title(f"Price (USD): {base}/{quote} ({CHAIN_ID})")
    plt.xlabel("Time (UTC)")
    plt.ylabel("Price USD")
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, f"{label}_price.png"), dpi=150)
    plt.close()

    # 2) Cumulative return
    plt.figure()
    ret["cum_return"].plot()
    plt.title(f"Cumulative Return: {base}/{quote} ({CHAIN_ID})")
    plt.xlabel("Time (UTC)")
    plt.ylabel("Cumulative Return")
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, f"{label}_cum_return.png"), dpi=150)
    plt.close()

    # 3) Return histogram (arith)
    plt.figure()
    ret["r_arith"].dropna().hist(bins=50)
    plt.title(f"Return Histogram: {base}/{quote} ({CHAIN_ID})")
    plt.xlabel("Arithmetic Return")
    plt.ylabel("Frequency")
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, f"{label}_return_hist.png"), dpi=150)
    plt.close()

    # 4) Rolling volatility (annualized)
    plt.figure()
    ret["roll_vol_ann"].plot()
    plt.title(f"Rolling Volatility (ann., window={ROLLING_WINDOW}): {base}/{quote} ({CHAIN_ID})")
    plt.xlabel("Time (UTC)")
    plt.ylabel("Annualized Volatility")
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, f"{label}_rolling_vol.png"), dpi=150)
    plt.close()

    print(f"\nSaved plots to ./{OUT_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
