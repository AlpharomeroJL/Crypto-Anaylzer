#!/usr/bin/env python3
"""
Materialize resampled OHLCV-style bars into SQLite tables bars_{freq}.
- 5min, 15min, 1h: from snapshots.
- 1D: from bars_1h (open=first, high=max, low=min, close=last; liquidity/vol=last).
Idempotent: UPSERT so safe to run daily.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crypto_analyzer.config import bars_freqs, db_path
from crypto_analyzer.data import load_bars, load_snapshots
from crypto_analyzer.features import cumulative_returns_log, log_returns, rolling_volatility


def _bars_table_schema(table: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {table} (
        ts_utc TEXT NOT NULL,
        chain_id TEXT NOT NULL,
        pair_address TEXT NOT NULL,
        base_symbol TEXT,
        quote_symbol TEXT,
        open REAL,
        high REAL,
        low REAL,
        close REAL NOT NULL,
        log_return REAL,
        cum_return REAL,
        roll_vol REAL,
        liquidity_usd REAL,
        vol_h24 REAL,
        PRIMARY KEY (ts_utc, chain_id, pair_address)
    );
    """


def _ensure_bars_table(conn: sqlite3.Connection, table: str) -> None:
    conn.execute(_bars_table_schema(table))
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_ts ON {table}(ts_utc);")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_pair ON {table}(chain_id, pair_address);")
    conn.commit()


def _resample_pair(
    g: pd.DataFrame,
    freq: str,
    window: int,
) -> Optional[pd.DataFrame]:
    """Resample one pair's snapshots to bars. Returns DataFrame or None if too few points."""
    g = g.sort_values("ts_utc").set_index("ts_utc")
    price = g["price_usd"]
    ohlc = price.resample(freq).ohlc()
    ohlc.columns = ["open", "high", "low", "close"]
    ohlc = ohlc.dropna(subset=["close"])
    if len(ohlc) < max(2, window + 1):
        return None
    # Sanity: non-negative OHLC, no NaNs in close after resample
    if (ohlc <= 0).any().any() or ohlc["close"].isna().any():
        return None
    ohlc["log_return"] = log_returns(ohlc["close"]).values
    ohlc["cum_return"] = cumulative_returns_log(ohlc["log_return"]).values
    ohlc["roll_vol"] = rolling_volatility(ohlc["log_return"], window).values
    liq = g["liquidity_usd"].resample(freq).last()
    vol24 = g["vol_h24"].resample(freq).last()
    ohlc["liquidity_usd"] = liq.reindex(ohlc.index).ffill().bfill()
    ohlc["vol_h24"] = vol24.reindex(ohlc.index).ffill().bfill()
    ohlc["chain_id"] = g["chain_id"].iloc[0]
    ohlc["pair_address"] = g["pair_address"].iloc[0]
    ohlc["base_symbol"] = g["base_symbol"].iloc[-1]
    ohlc["quote_symbol"] = g["quote_symbol"].iloc[-1]
    ohlc["ts_utc"] = ohlc.index
    return ohlc.reset_index(drop=True)


def _default_window_for_freq(freq: str) -> int:
    """Rolling vol window: 1h=24, 5min=288, 15min=96, 1D=7."""
    f = freq.replace(" ", "").upper()
    if f == "1H":
        return 24
    if f == "1D":
        return 7
    if "MIN" in f:
        m = int("".join(c for c in f if c.isdigit()) or "5")
        return 288 if m <= 5 else (96 if m <= 15 else 48)
    return 24


def _materialize_1d_from_1h(path: str, window: int) -> int:
    """
    Build bars_1D from bars_1h: resample OHLC (open=first, high=max, low=min, close=last),
    liquidity_usd/vol_h24=last; compute log_return, cum_return, roll_vol. UPSERT into bars_1D.
    """
    table = "bars_1D"
    try:
        bars_1h = load_bars("1h", db_path_override=path, min_bars=None)
    except FileNotFoundError:
        print(f"{table}: bars_1h not found. Run: python materialize_bars.py --freq 1h")
        return 0
    if bars_1h.empty:
        print(f"{table}: no 1h bars.")
        return 0

    bars_1h["ts_utc"] = pd.to_datetime(bars_1h["ts_utc"], utc=True)
    rows_to_insert = []
    for (chain_id, pair_address), g in bars_1h.groupby(["chain_id", "pair_address"]):
        g = g.sort_values("ts_utc").set_index("ts_utc")
        resampled = (
            g.resample("1D")
            .agg(
                open=("open", "first"),
                high=("high", "max"),
                low=("low", "min"),
                close=("close", "last"),
                liquidity_usd=("liquidity_usd", "last"),
                vol_h24=("vol_h24", "last"),
                base_symbol=("base_symbol", "last"),
                quote_symbol=("quote_symbol", "last"),
            )
            .dropna(subset=["close"])
        )
        if len(resampled) < 2:
            continue
        if (resampled[["open", "high", "low", "close"]] <= 0).any().any():
            continue
        resampled["log_return"] = log_returns(resampled["close"]).values
        resampled["cum_return"] = cumulative_returns_log(resampled["log_return"]).values
        resampled["roll_vol"] = rolling_volatility(resampled["log_return"], window).values
        for ts, row in resampled.iterrows():
            rows_to_insert.append(
                (
                    ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                    chain_id,
                    pair_address,
                    row.get("base_symbol"),
                    row.get("quote_symbol"),
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    float(row["log_return"]) if pd.notna(row["log_return"]) else None,
                    float(row["cum_return"]) if pd.notna(row["cum_return"]) else None,
                    float(row["roll_vol"]) if pd.notna(row["roll_vol"]) else None,
                    float(row["liquidity_usd"]) if pd.notna(row["liquidity_usd"]) else None,
                    float(row["vol_h24"]) if pd.notna(row["vol_h24"]) else None,
                )
            )

    if not rows_to_insert:
        print(f"{table}: no bars generated (need more 1h bars).")
        return 0

    with sqlite3.connect(path) as conn:
        _ensure_bars_table(conn, table)
        conn.executemany(
            """
            INSERT OR REPLACE INTO bars_1D
            (ts_utc, chain_id, pair_address, base_symbol, quote_symbol,
             open, high, low, close, log_return, cum_return, roll_vol,
             liquidity_usd, vol_h24)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows_to_insert,
        )
        conn.commit()

    print(f"{table}: inserted {len(rows_to_insert)} rows (from bars_1h).")
    return len(rows_to_insert)


def materialize_freq(
    path: str,
    freq: str,
    window: Optional[int] = None,
) -> int:
    """
    Build or update bars for one frequency. Idempotent (UPSERT).
    For 1D: load from bars_1h, resample OHLC, then UPSERT into bars_1D.
    For 5min/15min/1h: load from snapshots, resample, UPSERT.
    """
    freq_norm = freq.replace(" ", "").upper()
    if freq_norm == "1D":
        win = window if window is not None else _default_window_for_freq("1D")
        return _materialize_1d_from_1h(path, win)

    table = f"bars_{freq.replace(' ', '')}"
    win = window if window is not None else _default_window_for_freq(freq)
    df = load_snapshots(db_path_override=path, apply_filters=True)
    if df.empty:
        print("No snapshot data. Run poller first.")
        return 0

    df["pair_id"] = df["chain_id"].astype(str) + ":" + df["pair_address"].astype(str)
    with sqlite3.connect(path) as conn:
        _ensure_bars_table(conn, table)

    rows_to_insert = []
    for pair_id, g in df.groupby("pair_id"):
        bar_df = _resample_pair(g, freq, win)
        if bar_df is None:
            continue
        for _, row in bar_df.iterrows():
            rows_to_insert.append(
                (
                    row["ts_utc"].isoformat() if hasattr(row["ts_utc"], "isoformat") else str(row["ts_utc"]),
                    row["chain_id"],
                    row["pair_address"],
                    row.get("base_symbol"),
                    row.get("quote_symbol"),
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    float(row["log_return"]) if pd.notna(row["log_return"]) else None,
                    float(row["cum_return"]) if pd.notna(row["cum_return"]) else None,
                    float(row["roll_vol"]) if pd.notna(row["roll_vol"]) else None,
                    float(row["liquidity_usd"]) if pd.notna(row["liquidity_usd"]) else None,
                    float(row["vol_h24"]) if pd.notna(row["vol_h24"]) else None,
                )
            )

    if not rows_to_insert:
        print(f"{table}: no bars generated (try coarser freq or more data).")
        return 0

    chunk_size = 500
    with sqlite3.connect(path) as conn:
        for i in range(0, len(rows_to_insert), chunk_size):
            chunk = rows_to_insert[i : i + chunk_size]
            conn.executemany(
                f"""
                INSERT OR REPLACE INTO {table}
                (ts_utc, chain_id, pair_address, base_symbol, quote_symbol,
                 open, high, low, close, log_return, cum_return, roll_vol,
                 liquidity_usd, vol_h24)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                chunk,
            )
        conn.commit()

    print(f"{table}: inserted {len(rows_to_insert)} rows.")
    return len(rows_to_insert)


def main() -> int:
    ap = argparse.ArgumentParser(description="Materialize resampled bars from snapshots")
    ap.add_argument("--db", default=None, help="SQLite path (default: config)")
    ap.add_argument("--freq", default=None, help="Single freq to build (e.g. 5min). If omitted, build all from config.")
    ap.add_argument("--window", type=int, default=None, help="Rolling vol window in bars")
    args = ap.parse_args()

    path = args.db or (db_path() if callable(db_path) else db_path())
    freqs = [args.freq] if args.freq else (bars_freqs() if callable(bars_freqs) else ["5min", "15min", "1h", "1D"])
    total = 0
    for f in freqs:
        total += materialize_freq(path, f, window=args.window)
    return 0 if total >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
