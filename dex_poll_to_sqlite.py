#!/usr/bin/env python3
"""
Poll:
- Spot SOL/ETH/BTC from Coinbase (primary) or Kraken (fallback) -> spot_price_snapshots
- Multiple Dexscreener pairs (config or CLI) -> sol_monitor_snapshots (one row per pair per cycle)

Stores into SQLite for returns/volatility and multi-pair bars.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# When --log-file is set, all output is also appended here (for Windows service).
_log_file: Optional[Any] = None


def _log(msg: str) -> None:
    print(msg, flush=True)
    if _log_file is not None:
        try:
            _log_file.write(msg + "\n")
            _log_file.flush()
        except Exception:
            pass

DB_PATH = "dex_data.sqlite"

DEX_BASE_URL = "https://api.dexscreener.com"
COINBASE_URL = "https://api.coinbase.com"
KRAKEN_URL = "https://api.kraken.com"

CHAIN_ID = "solana"
# Orca SOL/USDC (Dexscreener returns data). Fallback when config has no pairs.
PAIR_ADDRESS = "Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE"
DEFAULT_DEX_PAIRS: List[Dict[str, str]] = [
    {"chain_id": CHAIN_ID, "pair_address": PAIR_ADDRESS, "label": "SOL/USDC"},
]

# Multi-asset spot feeds: (symbol, Coinbase product, Kraken pair). Kraken uses XBT for BTC.
SPOT_ASSETS = [
    ("SOL", "SOL-USD", "SOLUSD"),
    ("ETH", "ETH-USD", "ETHUSD"),
    ("BTC", "BTC-USD", "XBTUSD"),
]

# Default 60s for 1-min bars; override with --interval.
POLL_EVERY_SECONDS = 60
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


def pick_pair_from_dex_payload(data: dict) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected Dex response type: {type(data)}")

    # Prefer single pair object if present (accept any dict, including empty)
    p = data.get("pair")
    if isinstance(p, dict):
        return p
    if isinstance(p, list) and p and isinstance(p[0], dict):
        return p[0]

    # Fallback: pairs as list or single object
    pairs = data.get("pairs")
    if isinstance(pairs, dict):
        return pairs
    if isinstance(pairs, list):
        for item in pairs:
            if isinstance(item, dict):
                return item

    # Top-level payload is the pair (e.g. unwrapped)
    if data.get("chainId") and (data.get("priceUsd") is not None or data.get("liquidity")):
        return data

    # API returned pair=null, pairs=null (pair may be delisted or invalid)
    if data.get("pair") is None and data.get("pairs") is None:
        raise RuntimeError(
            "Dex returned no data for this pair (pair may be delisted or invalid). "
            "Try --pairAddress with a different pool (e.g. Orca SOL/USDC: Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE)."
        )
    raise RuntimeError(f"Unexpected Dex response shape. Top-level keys: {list(data.keys())}")


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

            if isinstance(data, dict) and (data.get("error") or data.get("message")):
                err = data.get("error") or data.get("message")
                raise RuntimeError(f"Dex API error: {err}")

            if isinstance(data, list) and data and isinstance(data[0], dict):
                return data[0]
            if isinstance(data, dict):
                return pick_pair_from_dex_payload(data)
            raise RuntimeError(f"Unexpected Dex response type: {type(data)}")
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


def fetch_dex_universe_top_pairs(
    chain_id: str = "solana",
    page_size: int = 50,
    min_liquidity_usd: float = 250_000,
    min_vol_h24: float = 500_000,
) -> List[Dict[str, str]]:
    """
    Fetch top DEX pairs for a chain via Dexscreener search API.
    Uses public search endpoint; filters by liquidity and volume.
    Returns list of {chain_id, pair_address, label}. Empty on failure (caller should fall back to config pairs).
    """
    # Search by chain-native token to get pairs on that chain
    query_map = {"solana": "SOL", "ethereum": "ETH", "bsc": "BNB", "base": "ETH", "arbitrum": "ETH", "polygon": "MATIC"}
    query = query_map.get(chain_id.lower(), "SOL")
    url = f"{DEX_BASE_URL}/latest/dex/search?q={query}"
    try:
        r = requests.get(url, timeout=HTTP_TIMEOUT_S)
        if r.status_code == 429:
            time.sleep(2.0)
            r = requests.get(url, timeout=HTTP_TIMEOUT_S)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        _log(f"Universe fetch failed: {e}. Using configured pairs.")
        return []

    pairs_raw = data.get("pairs") if isinstance(data, dict) else None
    if not isinstance(pairs_raw, list):
        return []

    out: List[Dict[str, str]] = []
    seen: set = set()
    for item in pairs_raw:
        if not isinstance(item, dict):
            continue
        cid = (item.get("chainId") or "").strip().lower()
        if cid != chain_id.lower():
            continue
        addr = (item.get("pairAddress") or item.get("dexId") or "").strip()
        if not addr or addr in seen:
            continue
        liq = to_float(safe_get(item, "liquidity.usd"))
        vol = to_float(safe_get(item, "volume.h24"))
        if liq is not None and liq < min_liquidity_usd:
            continue
        if vol is not None and vol < min_vol_h24:
            continue
        base = (safe_get(item, "baseToken.symbol") or "").strip() or "?"
        quote = (safe_get(item, "quoteToken.symbol") or "").strip() or "?"
        label = f"{base}/{quote}" if base and quote else f"{chain_id}/{addr[:8]}"
        seen.add(addr)
        out.append({"chain_id": chain_id, "pair_address": addr, "label": label})
        if len(out) >= page_size:
            break
    return out


def load_universe_config(config_path: str) -> Dict[str, Any]:
    """Load universe section from config YAML. Returns dict with enabled, chain_id, page_size, refresh_minutes, min_liquidity_usd, min_vol_h24."""
    path = Path(config_path)
    defaults = {"enabled": False, "chain_id": "solana", "page_size": 50, "refresh_minutes": 60, "min_liquidity_usd": 250_000, "min_vol_h24": 500_000}
    if not path.exists():
        return defaults
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return defaults
    if not isinstance(data, dict):
        return defaults
    u = data.get("universe") or {}
    return {**defaults, **{k: u[k] for k in defaults if k in u and u[k] is not None}}


def load_dex_pairs_from_config(config_path: str) -> List[Dict[str, str]]:
    """
    Read DEX pairs from config YAML key `pairs`. Each item: chain_id, pair_address, label (optional).
    If PyYAML missing but file exists, log a message and return [].
    """
    path = Path(config_path)
    if not path.exists():
        return []
    try:
        import yaml
    except ImportError:
        _log("Config file present but PyYAML not installed. pip install PyYAML to use config pairs. Using defaults.")
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        _log(f"Could not load config {config_path}: {e}. Using defaults.")
        return []
    if not isinstance(data, dict):
        return []
    pairs = data.get("pairs")
    if not pairs or not isinstance(pairs, list):
        return []
    out: List[Dict[str, str]] = []
    for item in pairs:
        if not isinstance(item, dict):
            continue
        cid = item.get("chain_id") or item.get("chainId")
        addr = item.get("pair_address") or item.get("pairAddress")
        if not cid or not addr:
            continue
        out.append({
            "chain_id": str(cid).strip(),
            "pair_address": str(addr).strip(),
            "label": str(item.get("label", "")).strip() or f"{cid}/{addr[:8]}",
        })
    return out


def insert_snapshot(
    conn: sqlite3.Connection,
    ts: str,
    pair: Dict[str, Any],
    bpx: float,
    chain_id: str = CHAIN_ID,
    pair_address: str = PAIR_ADDRESS,
) -> None:
    row = {
        "ts_utc": ts,
        "chain_id": chain_id,
        "pair_address": pair_address,
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


def poll_one_dex_pair(
    conn: sqlite3.Connection,
    ts: str,
    chain_id: str,
    pair_address: str,
    spot_price_sol: float,
    label: str = "",
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Fetch one DEX pair and insert one row into sol_monitor_snapshots.
    Returns (True, pair_dict for logging) or (False, None) on failure.
    """
    try:
        pair = fetch_dex_pair(chain_id, pair_address)
        insert_snapshot(conn, ts, pair, spot_price_sol, chain_id, pair_address)
        return True, pair
    except Exception as e:
        _log(f"WARN dex {chain_id}:{pair_address} {e}")
        return False, None


def insert_spot_prices(
    conn: sqlite3.Connection, ts: str, prices: List[Tuple[str, float]]
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
    global _log_file
    parser = argparse.ArgumentParser(description="Poll Dexscreener + spot prices into SQLite")
    parser.add_argument("--config", default="config.yaml", help="Path to config YAML (default: config.yaml)")
    parser.add_argument("--pairs-from-config", dest="pairs_from_config", action="store_true", default=True, help="Load DEX pairs from config (default)")
    parser.add_argument("--no-pairs-from-config", dest="pairs_from_config", action="store_false", help="Disable config pairs; use single default or --pair only")
    parser.add_argument("--pair", action="append", default=[], metavar="CHAIN_ID:PAIR_ADDRESS", help="Add DEX pair (repeatable); e.g. solana:Czfq3xZZ...")
    parser.add_argument("--pair-delay", type=float, default=0.2, metavar="SEC", help="Seconds between DEX API calls (default: 0.2)")
    parser.add_argument("--chainId", default=CHAIN_ID, help=f"Chain id for legacy single pair (default: {CHAIN_ID})")
    parser.add_argument("--pairAddress", default=PAIR_ADDRESS, help="DEX pair address for legacy single pair")
    parser.add_argument("--interval", type=int, default=POLL_EVERY_SECONDS, help="Poll interval in seconds (default: 60)")
    parser.add_argument("--log-file", default=None, help="Also append all output to this file (for Windows service)")
    parser.add_argument("--universe", nargs="?", const="top", default=None, metavar="top", help="Enable universe mode: use --universe or --universe top. Other flags: --universe-chain, --universe-page-size, etc.")
    parser.add_argument("--universe-chain", default="solana", help="Chain for universe fetch (default: solana)")
    parser.add_argument("--universe-page-size", type=int, default=50, metavar="N", help="Max pairs to keep in universe (default: 50)")
    parser.add_argument("--universe-refresh-minutes", type=float, default=60, metavar="M", help="Refresh universe allowlist every M minutes (default: 60)")
    parser.add_argument("--universe-min-liquidity", type=float, default=250_000, help="Min liquidity USD for universe pairs (default: 250000)")
    parser.add_argument("--universe-min-vol-h24", type=float, default=500_000, help="Min 24h volume USD for universe pairs (default: 500000)")
    args = parser.parse_args()
    interval_sec = args.interval

    # Universe mode: refresh allowlist periodically (--universe or --universe top)
    universe_enabled = (getattr(args, "universe", None) == "top")
    universe_refresh_sec = max(60, float(getattr(args, "universe_refresh_minutes", 60)) * 60)
    universe_last_refresh: List[Optional[float]] = [None]
    universe_cache: List[Optional[List[Dict[str, str]]]] = [None]

    def _get_universe_pairs() -> List[Dict[str, str]]:
        if not universe_enabled:
            return []
        now = time.time()
        if universe_last_refresh[0] is None or (now - universe_last_refresh[0]) >= universe_refresh_sec:
            cfg = load_universe_config(args.config)
            chain = getattr(args, "universe_chain", "solana") or cfg.get("chain_id", "solana")
            page_size = getattr(args, "universe_page_size", None) or cfg.get("page_size", 50)
            min_liq = getattr(args, "universe_min_liquidity", None) or cfg.get("min_liquidity_usd", 250_000)
            min_vol = getattr(args, "universe_min_vol_h24", None) or cfg.get("min_vol_h24", 500_000)
            pairs = fetch_dex_universe_top_pairs(chain_id=chain, page_size=page_size, min_liquidity_usd=min_liq, min_vol_h24=min_vol)
            universe_last_refresh[0] = now
            universe_cache[0] = pairs
            if pairs:
                _log(f"Universe refreshed: {len(pairs)} pairs (chain={chain})")
            return pairs
        return universe_cache[0] or []

    # Build dex_pairs list
    dex_pairs: List[Dict[str, str]] = []
    if universe_enabled:
        dex_pairs = _get_universe_pairs()
    if not dex_pairs and args.pairs_from_config:
        dex_pairs = load_dex_pairs_from_config(args.config)
    if not dex_pairs:
        dex_pairs = list(DEFAULT_DEX_PAIRS)
    for raw in args.pair:
        if ":" in raw:
            cid, addr = raw.split(":", 1)
            dex_pairs.append({
                "chain_id": cid.strip(),
                "pair_address": addr.strip(),
                "label": f"{cid.strip()}/{addr.strip()[:8]}",
            })

    if getattr(args, "log_file", None):
        log_path = getattr(args, "log_file")
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        _log_file = open(log_path, "a", encoding="utf-8")

    conn = sqlite3.connect(DB_PATH)
    ensure_db(conn)

    # Mutable ref so universe mode can refresh the list each cycle
    current_dex_pairs: List[List[Dict[str, str]]] = [dex_pairs]
    _log(f"Writing to SQLite: {DB_PATH}")
    _log(f"Dex pairs: {len(dex_pairs)}  (universe_mode={universe_enabled})")
    _log(f"Spot assets: {[s[0] for s in SPOT_ASSETS]}")
    _log(f"Price feed: Coinbase (primary) / Kraken (fallback)")
    _log(f"Poll every {interval_sec}s. Pair delay {args.pair_delay}s. Stop with Ctrl+C.\n")

    try:
        while True:
            if universe_enabled:
                u = _get_universe_pairs()
                if u:
                    current_dex_pairs[0] = u
            dex_pairs_this_cycle = current_dex_pairs[0]
            ts = utc_now_iso()
            try:
                # A) Spot polling (unchanged)
                spot_prices: List[Tuple[str, float]] = []
                for symbol, cb_product, kraken_pair in SPOT_ASSETS:
                    px = fetch_spot_price_asset(cb_product, kraken_pair)
                    spot_prices.append((symbol, px))
                sol_price = spot_prices[0][1]
                insert_spot_prices(conn, ts, spot_prices)

                # B) DEX pairs: one row per pair per cycle
                dex_summaries: List[str] = []
                for i, p in enumerate(dex_pairs_this_cycle):
                    ok, pair = poll_one_dex_pair(
                        conn, ts,
                        p["chain_id"], p["pair_address"],
                        sol_price,
                        label=p.get("label", ""),
                    )
                    if ok and pair is not None:
                        liq = safe_get(pair, "liquidity.usd")
                        vol = safe_get(pair, "volume.h24")
                        lbl = p.get("label", "") or f"{safe_get(pair, 'baseToken.symbol')}/{safe_get(pair, 'quoteToken.symbol')}"
                        dex_summaries.append(f"[{lbl} liq={liq} vol24={vol}]")
                    if i < len(dex_pairs_this_cycle) - 1 and args.pair_delay > 0:
                        time.sleep(args.pair_delay)

                conn.commit()

                spot_str = "  ".join(f"{s}={p:.2f}" for s, p in spot_prices)
                dex_str = f"  dex_pairs={len(dex_pairs_this_cycle)} " + " ".join(dex_summaries) if dex_summaries else f"  dex_pairs={len(dex_pairs_this_cycle)} (no ok)"
                _log(f"{ts}  OK  {spot_str}{dex_str}")
            except Exception as e:
                _log(f"{ts}  ERR  {e}")

            time.sleep(interval_sec)

    except KeyboardInterrupt:
        _log("\nStopped.")
    finally:
        if _log_file is not None:
            try:
                _log_file.close()
            except Exception:
                pass
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
