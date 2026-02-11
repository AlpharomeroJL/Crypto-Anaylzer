#!/usr/bin/env python3
"""
Step 2: Poll Dexscreener pair snapshots and store them to SQLite.

Run:
  python dex_poll_to_sqlite.py

Stop with Ctrl+C.

After you collect data, you can build time series + returns/vol next.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

BASE_URL = "https://api.dexscreener.com"
DB_PATH = "dex_data.sqlite"

# --- CONFIG: put the pairs you want to track here ---
# From your output: chainId="solana", pairAddress="GMUqPT96t2m2tTVteTXyCUGWzvH2RjQreUvtrtX23UdG", etc.
TRACKED_PAIRS = [
    ("solana", "AvSUmeK93LAo2DGZaojQuU3WFCGB895L2CzUgdEewZEX"),  # SOL/USDC (raydium) ✅
]

POLL_EVERY_SECONDS = 60  # 60s is fine to start; later you can do 10s/30s, but mind rate limits.
HTTP_TIMEOUT_S = 15.0
RETRIES = 3


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pair_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc TEXT NOT NULL,
            chain_id TEXT NOT NULL,
            pair_address TEXT NOT NULL,

            dex_id TEXT,
            base_symbol TEXT,
            base_address TEXT,
            quote_symbol TEXT,
            quote_address TEXT,

            price_usd REAL,
            price_native REAL,

            liquidity_usd REAL,

            vol_h24 REAL,
            vol_h6 REAL,
            vol_h1 REAL,
            vol_m5 REAL,

            txns_h24_buys INTEGER,
            txns_h24_sells INTEGER,
            txns_h1_buys INTEGER,
            txns_h1_sells INTEGER,
            txns_m5_buys INTEGER,
            txns_m5_sells INTEGER,

            raw_json TEXT
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pair_snapshots_pair_ts ON pair_snapshots(chain_id, pair_address, ts_utc);"
    )
    conn.commit()


def safe_get(d: Dict[str, Any], path: str, default: Any = None) -> Any:
    cur: Any = d
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)
    except Exception:
        return None


def to_int(x: Any) -> Optional[int]:
    if x is None:
        return None
    try:
        return int(x)
    except Exception:
        return None


def fetch_pair(chain_id: str, pair_address: str) -> Dict[str, Any]:
    url = f"{BASE_URL}/latest/dex/pairs/{chain_id}/{pair_address}"

    last_err: Optional[str] = None
    for attempt in range(1, RETRIES + 1):
        try:
            resp = requests.get(url, timeout=HTTP_TIMEOUT_S)
            if resp.status_code == 429:
                wait_s = 1.5 * attempt
                time.sleep(wait_s)
                last_err = f"HTTP 429 rate limit; waited {wait_s:.1f}s"
                continue
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            # Shape is typically {"pair": {...}} or {"pairs": [...]} depending on endpoint behavior;
            # handle both defensively.
            if "pair" in data and isinstance(data["pair"], dict):
                return data["pair"]
            if "pairs" in data and isinstance(data["pairs"], list) and data["pairs"]:
                return data["pairs"][0]
            raise RuntimeError("Unexpected response shape (no 'pair' or non-empty 'pairs').")
        except (requests.RequestException, ValueError, RuntimeError) as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(0.5 * attempt)

    raise RuntimeError(f"Failed to fetch pair after {RETRIES} tries. Last error: {last_err}")


def insert_snapshot(conn: sqlite3.Connection, ts_utc: str, chain_id: str, pair_address: str, p: Dict[str, Any]) -> None:
    row = {
        "ts_utc": ts_utc,
        "chain_id": chain_id,
        "pair_address": pair_address,

        "dex_id": p.get("dexId"),
        "base_symbol": safe_get(p, "baseToken.symbol"),
        "base_address": safe_get(p, "baseToken.address"),
        "quote_symbol": safe_get(p, "quoteToken.symbol"),
        "quote_address": safe_get(p, "quoteToken.address"),

        "price_usd": to_float(p.get("priceUsd")),
        "price_native": to_float(p.get("priceNative")),

        "liquidity_usd": to_float(safe_get(p, "liquidity.usd")),

        "vol_h24": to_float(safe_get(p, "volume.h24")),
        "vol_h6": to_float(safe_get(p, "volume.h6")),
        "vol_h1": to_float(safe_get(p, "volume.h1")),
        "vol_m5": to_float(safe_get(p, "volume.m5")),

        "txns_h24_buys": to_int(safe_get(p, "txns.h24.buys")),
        "txns_h24_sells": to_int(safe_get(p, "txns.h24.sells")),
        "txns_h1_buys": to_int(safe_get(p, "txns.h1.buys")),
        "txns_h1_sells": to_int(safe_get(p, "txns.h1.sells")),
        "txns_m5_buys": to_int(safe_get(p, "txns.m5.buys")),
        "txns_m5_sells": to_int(safe_get(p, "txns.m5.sells")),

        "raw_json": json.dumps(p, separators=(",", ":"), ensure_ascii=False),
    }

    conn.execute(
        """
        INSERT INTO pair_snapshots (
            ts_utc, chain_id, pair_address,
            dex_id, base_symbol, base_address, quote_symbol, quote_address,
            price_usd, price_native, liquidity_usd,
            vol_h24, vol_h6, vol_h1, vol_m5,
            txns_h24_buys, txns_h24_sells, txns_h1_buys, txns_h1_sells, txns_m5_buys, txns_m5_sells,
            raw_json
        ) VALUES (
            :ts_utc, :chain_id, :pair_address,
            :dex_id, :base_symbol, :base_address, :quote_symbol, :quote_address,
            :price_usd, :price_native, :liquidity_usd,
            :vol_h24, :vol_h6, :vol_h1, :vol_m5,
            :txns_h24_buys, :txns_h24_sells, :txns_h1_buys, :txns_h1_sells, :txns_m5_buys, :txns_m5_sells,
            :raw_json
        );
        """,
        row,
    )


def main() -> int:
    if not TRACKED_PAIRS:
        print("No TRACKED_PAIRS configured. Add at least one (chainId, pairAddress).")
        return 1

    conn = sqlite3.connect(DB_PATH)
    ensure_db(conn)

    print(f"Writing to SQLite: {DB_PATH}")
    print(f"Tracking {len(TRACKED_PAIRS)} pair(s). Poll every {POLL_EVERY_SECONDS}s.")
    print("Stop with Ctrl+C.\n")

    try:
        while True:
            cycle_ts = utc_now_iso()
            ok = 0
            for (chain_id, pair_address) in TRACKED_PAIRS:
                try:
                    p = fetch_pair(chain_id, pair_address)
                    insert_snapshot(conn, cycle_ts, chain_id, pair_address, p)
                    conn.commit()
                    ok += 1

                    base = safe_get(p, "baseToken.symbol", "?")
                    quote = safe_get(p, "quoteToken.symbol", "?")
                    price = p.get("priceUsd", None)
                    liq = safe_get(p, "liquidity.usd", None)
                    print(f"{cycle_ts}  OK  {chain_id:<8} {base}/{quote:<10} priceUsd={price} liqUsd={liq}")

                except Exception as e:
                    print(f"{cycle_ts}  ERR {chain_id:<8} pair={pair_address}  {e}")

            # sleep until next cycle
            time.sleep(POLL_EVERY_SECONDS)

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())