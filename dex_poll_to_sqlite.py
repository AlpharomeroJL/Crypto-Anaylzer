#!/usr/bin/env python3
"""
Poll:
- Dexscreener pair metrics (liquidity/volume/txns) for SOL/USDC pool
- Spot SOL price from Coinbase (primary) or Kraken (fallback) for returns/volatility

Stores into SQLite so you can compute returns/volatility cleanly.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

DB_PATH = "dex_data.sqlite"

DEX_BASE_URL = "https://api.dexscreener.com"
COINBASE_URL = "https://api.coinbase.com"
KRAKEN_URL = "https://api.kraken.com"

CHAIN_ID = "solana"
PAIR_ADDRESS = "AvSUmeK93LAo2DGZaojQuU3WFCGB895L2CzUgdEewZEX"  # SOL/USDC pool you selected

# Multi-asset spot feeds: (symbol, Coinbase product, Kraken pair). Kraken uses XBT for BTC.
SPOT_ASSETS = [
    ("SOL", "SOL-USD", "SOLUSD"),
    ("ETH", "ETH-USD", "ETHUSD"),
    ("BTC", "BTC-USD", "XBTUSD"),
]

# 10s polling → 300 resampled points in ~50 min (analyzer uses 10s resample). Watch for API rate limits.
POLL_EVERY_SECONDS = 10
HTTP_TIMEOUT_S = 15.0
RETRIES = 3


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def ensure_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sol_monitor_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc TEXT NOT NULL,

            chain_id TEXT NOT NULL,
            pair_address TEXT NOT NULL,
            dex_id TEXT,
            base_symbol TEXT,
            quote_symbol TEXT,

            -- Dex metrics
            dex_price_usd REAL,
            dex_price_native REAL,
            liquidity_usd REAL,
            vol_h24 REAL,
            txns_h24_buys INTEGER,
            txns_h24_sells INTEGER,

            -- External "true" price feed for returns/vol
            spot_source TEXT,
            spot_price_usd REAL,

            raw_pair_json TEXT
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sol_monitor_ts ON sol_monitor_snapshots(ts_utc);")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS spot_price_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc TEXT NOT NULL,
            symbol TEXT NOT NULL,
            spot_price_usd REAL NOT NULL,
            spot_source TEXT
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_spot_ts_symbol ON spot_price_snapshots(ts_utc, symbol);"
    )
    conn.commit()


def fetch_dex_pair(chain_id: str, pair_address: str) -> Dict[str, Any]:
    url = f"{DEX_BASE_URL}/latest/dex/pairs/{chain_id}/{pair_address}"
    last_err: Optional[str] = None

    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(url, timeout=HTTP_TIMEOUT_S)
            if r.status_code == 429:
                time.sleep(1.5 * attempt)
                last_err = "HTTP 429"
                continue
            r.raise_for_status()
            data = r.json()

            if "pair" in data and isinstance(data["pair"], dict):
                return data["pair"]
            if "pairs" in data and isinstance(data["pairs"], list) and data["pairs"]:
                return data["pairs"][0]
            raise RuntimeError("Unexpected Dex response shape.")
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(0.5 * attempt)

    raise RuntimeError(f"Failed to fetch Dex pair. Last error: {last_err}")


def fetch_coinbase_price(product: str) -> float:
    # GET /v2/prices/SOL-USD/spot -> {"data":{"amount":"..."}}
    url = f"{COINBASE_URL}/v2/prices/{product}/spot"
    last_err: Optional[str] = None

    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(url, timeout=HTTP_TIMEOUT_S)
            if r.status_code == 429:
                time.sleep(1.5 * attempt)
                last_err = "HTTP 429"
                continue
            r.raise_for_status()
            data = r.json()
            px = to_float(safe_get(data, "data.amount"))
            if px is None:
                raise RuntimeError("Coinbase response missing data.amount")
            return px
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(0.5 * attempt)

    raise RuntimeError(f"Failed to fetch Coinbase price. Last error: {last_err}")


def fetch_kraken_price(pair: str) -> float:
    # GET /0/public/Ticker?pair=SOLUSD
    url = f"{KRAKEN_URL}/0/public/Ticker"
    params = {"pair": pair}
    last_err: Optional[str] = None

    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(url, params=params, timeout=HTTP_TIMEOUT_S)
            if r.status_code == 429:
                time.sleep(1.5 * attempt)
                last_err = "HTTP 429"
                continue
            r.raise_for_status()
            data = r.json()
            if data.get("error"):
                raise RuntimeError(f"Kraken error: {data['error']}")
            # Kraken result key can vary; take the first
            result = data.get("result", {})
            if not result:
                raise RuntimeError("Kraken response missing result")
            first_key = next(iter(result.keys()))
            # 'c' is last trade closed [price, lot volume]
            px = to_float(result[first_key].get("c", [None])[0])
            if px is None:
                raise RuntimeError("Kraken response missing last price")
            return px
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(0.5 * attempt)

    raise RuntimeError(f"Failed to fetch Kraken price. Last error: {last_err}")


def fetch_spot_price_asset(coinbase_product: str, kraken_pair: str) -> float:
    """Fetch one asset's USD price: Coinbase first, Kraken fallback."""
    try:
        return fetch_coinbase_price(coinbase_product)
    except Exception:
        return fetch_kraken_price(kraken_pair)


def fetch_spot_price_usd() -> float:
    """SOL only (backward compat). Prefer Coinbase, fallback Kraken."""
    sym, cb, kk = SPOT_ASSETS[0]
    return fetch_spot_price_asset(cb, kk)


def insert_snapshot(conn: sqlite3.Connection, ts: str, pair: Dict[str, Any], bpx: float) -> None:
    row = {
        "ts_utc": ts,
        "chain_id": CHAIN_ID,
        "pair_address": PAIR_ADDRESS,
        "dex_id": pair.get("dexId"),
        "base_symbol": safe_get(pair, "baseToken.symbol"),
        "quote_symbol": safe_get(pair, "quoteToken.symbol"),

        "dex_price_usd": to_float(pair.get("priceUsd")),
        "dex_price_native": to_float(pair.get("priceNative")),
        "liquidity_usd": to_float(safe_get(pair, "liquidity.usd")),
        "vol_h24": to_float(safe_get(pair, "volume.h24")),
        "txns_h24_buys": to_int(safe_get(pair, "txns.h24.buys")),
        "txns_h24_sells": to_int(safe_get(pair, "txns.h24.sells")),

        "spot_source": "coinbase_or_kraken",
        "spot_price_usd": bpx,

        "raw_pair_json": json.dumps(pair, separators=(",", ":"), ensure_ascii=False),
    }

    conn.execute(
        """
        INSERT INTO sol_monitor_snapshots (
            ts_utc,
            chain_id, pair_address, dex_id, base_symbol, quote_symbol,
            dex_price_usd, dex_price_native,
            liquidity_usd, vol_h24, txns_h24_buys, txns_h24_sells,
            spot_source, spot_price_usd,
            raw_pair_json
        ) VALUES (
            :ts_utc,
            :chain_id, :pair_address, :dex_id, :base_symbol, :quote_symbol,
            :dex_price_usd, :dex_price_native,
            :liquidity_usd, :vol_h24, :txns_h24_buys, :txns_h24_sells,
            :spot_source, :spot_price_usd,
            :raw_pair_json
        );
        """,
        row,
    )


def insert_spot_prices(
    conn: sqlite3.Connection, ts: str, prices: list[tuple[str, float]]
) -> None:
    """Insert one row per (ts, symbol, price) into spot_price_snapshots."""
    for symbol, px in prices:
        conn.execute(
            """
            INSERT INTO spot_price_snapshots (ts_utc, symbol, spot_price_usd, spot_source)
            VALUES (:ts_utc, :symbol, :spot_price_usd, 'coinbase_or_kraken');
            """,
            {"ts_utc": ts, "symbol": symbol, "spot_price_usd": px},
        )


def main() -> int:
    conn = sqlite3.connect(DB_PATH)
    ensure_db(conn)

    print(f"Writing to SQLite: {DB_PATH}")
    print(f"Dex pair: {CHAIN_ID}/{PAIR_ADDRESS}")
    print(f"Spot assets: {[s[0] for s in SPOT_ASSETS]}")
    print(f"Price feed: Coinbase (primary) / Kraken (fallback)")
    print(f"Poll every {POLL_EVERY_SECONDS}s. Stop with Ctrl+C.\n")

    try:
        while True:
            ts = utc_now_iso()
            try:
                pair = fetch_dex_pair(CHAIN_ID, PAIR_ADDRESS)
                spot_prices: list[tuple[str, float]] = []
                for symbol, cb_product, kraken_pair in SPOT_ASSETS:
                    px = fetch_spot_price_asset(cb_product, kraken_pair)
                    spot_prices.append((symbol, px))
                sol_price = spot_prices[0][1]

                insert_snapshot(conn, ts, pair, sol_price)
                insert_spot_prices(conn, ts, spot_prices)
                conn.commit()

                liq = safe_get(pair, "liquidity.usd")
                vol = safe_get(pair, "volume.h24")
                buys = safe_get(pair, "txns.h24.buys")
                sells = safe_get(pair, "txns.h24.sells")
                spot_str = "  ".join(f"{s}={p:.2f}" for s, p in spot_prices)

                print(
                    f"{ts}  OK  {spot_str}  "
                    f"dex_liqUsd={liq} dex_vol24={vol} dex_txns24={buys}/{sells}"
                )
            except Exception as e:
                print(f"{ts}  ERR  {e}")

            time.sleep(POLL_EVERY_SECONDS)

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
