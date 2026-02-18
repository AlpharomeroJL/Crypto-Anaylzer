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
import sys
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


# Stable tokens for universe stable/stable rejection (institutional default)
STABLE_SYMBOLS_UNIVERSE = frozenset(
    {"USDC", "USDT", "DAI", "USDP", "TUSD", "FDUSD", "USDE", "FRAX"}
)


def _universe_keep_pair(
    item: Dict[str, Any],
    min_liquidity_usd: float,
    min_vol_h24: float,
    quote_allowlist: Optional[List[str]] = None,
    reject_same_symbol: bool = True,
    reject_stable_stable: bool = True,
) -> Tuple[bool, str]:
    """
    Decide if a Dexscreener pair item passes universe quality gates.
    Returns (keep, reason). reason is rejection reason or "accept".
    Caller must filter by chain_id and use pairAddress (not dexId) as key.
    """
    liq = to_float(safe_get(item, "liquidity.usd"))
    vol = to_float(safe_get(item, "volume.h24"))
    if liq is None:
        return False, "missing liquidity"
    if vol is None:
        return False, "missing volume"
    base = (safe_get(item, "baseToken.symbol") or "").strip().upper()
    quote = (safe_get(item, "quoteToken.symbol") or "").strip().upper()
    if base == "" or quote == "":
        return False, "missing base or quote symbol"
    if base == "?" or quote == "?":
        return False, "unknown base or quote symbol"
    if reject_same_symbol and base == quote:
        return False, "base==quote"
    if quote_allowlist and quote not in {s.upper().strip() for s in quote_allowlist}:
        return False, f"quote {quote} not in allowlist"
    if reject_stable_stable and base in STABLE_SYMBOLS_UNIVERSE and quote in STABLE_SYMBOLS_UNIVERSE:
        return False, "stable/stable pair"
    if liq < min_liquidity_usd:
        return False, f"liq {liq} < {min_liquidity_usd}"
    if vol < min_vol_h24:
        return False, f"vol {vol} < {min_vol_h24}"
    return True, "accept"


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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS universe_allowlist (
            ts_utc TEXT NOT NULL,
            chain_id TEXT NOT NULL,
            pair_address TEXT NOT NULL,
            label TEXT,
            liquidity_usd REAL,
            vol_h24 REAL,
            source TEXT,
            query_summary TEXT,
            PRIMARY KEY (ts_utc, chain_id, pair_address)
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_universe_allowlist_ts ON universe_allowlist(ts_utc);")
    try:
        conn.execute("ALTER TABLE universe_allowlist ADD COLUMN reason_added TEXT;")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS universe_persistence (
            chain_id TEXT NOT NULL,
            pair_address TEXT NOT NULL,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            updated_ts TEXT NOT NULL,
            PRIMARY KEY (chain_id, pair_address)
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS universe_churn_log (
            ts_utc TEXT NOT NULL,
            chain_id TEXT NOT NULL,
            pair_address TEXT NOT NULL,
            action TEXT NOT NULL,
            reason TEXT,
            liquidity_usd REAL,
            vol_h24 REAL,
            PRIMARY KEY (ts_utc, chain_id, pair_address)
        );
        """
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


def _fmt_millions(x: Optional[float]) -> str:
    """Format number as e.g. 25.3m for debug output."""
    if x is None:
        return "?"
    if x >= 1e6:
        return f"{x / 1e6:.1f}m"
    if x >= 1e3:
        return f"{x / 1e3:.1f}k"
    return f"{x:.0f}"


# Default search queries per chain (broader discovery: SOL/USDC and orca return tradeable Solana pairs)
DEFAULT_UNIVERSE_QUERIES_BY_CHAIN: Dict[str, List[str]] = {
    "solana": ["USDC", "USDT", "SOL", "SOL/USDC", "orca"],
    "ethereum": ["USDC", "USDT", "ETH"],
    "base": ["USDC", "USDT", "ETH"],
    "arbitrum": ["USDC", "USDT", "ETH"],
    "polygon": ["USDC", "USDT", "ETH"],
    "bsc": ["USDC", "USDT", "BNB"],
}

def _universe_rank_key(p: Dict[str, Any]) -> Tuple[Any, ...]:
    """Sort key for deterministic selection: liquidity desc, volume desc, label asc, pair_address asc."""
    liq = p.get("liquidity_usd")
    vol = p.get("vol_h24")
    liq_val = -(float(liq)) if liq is not None else 0.0
    vol_val = -(float(vol)) if vol is not None else 0.0
    return (liq_val, vol_val, (p.get("label") or "").strip(), (p.get("pair_address") or "").strip())


def _load_persistence(
    conn: sqlite3.Connection,
    chain_id: str,
    pair_addrs: set,
) -> Dict[str, int]:
    """Return dict pair_address -> consecutive_failures for given chain and addrs."""
    out: Dict[str, int] = {}
    if not pair_addrs:
        return out
    placeholders = ",".join("?" for _ in pair_addrs)
    try:
        cur = conn.execute(
            f"SELECT pair_address, consecutive_failures FROM universe_persistence WHERE chain_id = ? AND pair_address IN ({placeholders})",
            [chain_id] + list(pair_addrs),
        )
        for row in cur.fetchall():
            out[row[0]] = int(row[1]) if row[1] is not None else 0
    except sqlite3.OperationalError:
        pass
    return out


def _update_persistence(
    conn: sqlite3.Connection,
    chain_id: str,
    ts_utc: str,
    prev_addrs: set,
    new_selected_addrs: set,
    min_k: int,
) -> None:
    """Update consecutive_failures: in new -> 0; not in new -> +1 (or 1 if new). Upsert universe_persistence."""
    for addr in prev_addrs:
        if not addr:
            continue
        if addr in new_selected_addrs:
            count = 0
        else:
            cur = conn.execute(
                "SELECT consecutive_failures FROM universe_persistence WHERE chain_id = ? AND pair_address = ?",
                (chain_id, addr),
            )
            row = cur.fetchone()
            count = (int(row[0]) + 1) if row and row[0] is not None else 1
        conn.execute(
            "INSERT OR REPLACE INTO universe_persistence (chain_id, pair_address, consecutive_failures, updated_ts) VALUES (?, ?, ?, ?)",
            (chain_id, addr, count, ts_utc),
        )
    for addr in new_selected_addrs:
        if addr and addr not in prev_addrs:
            conn.execute(
                "INSERT OR REPLACE INTO universe_persistence (chain_id, pair_address, consecutive_failures, updated_ts) VALUES (?, ?, ?, ?)",
                (chain_id, addr, 0, ts_utc),
            )
    conn.commit()


def _apply_churn_control(
    prev_pairs: List[Dict[str, Any]],
    new_pairs: List[Dict[str, Any]],
    page_size: int,
    max_churn_pct: float,
    conn: Optional[sqlite3.Connection] = None,
    chain_id: Optional[str] = None,
    ts_utc: Optional[str] = None,
    min_persistence_refreshes: int = 0,
) -> List[Dict[str, Any]]:
    """
    Limit replacements: keep all overlapping pairs; allow up to ceil(len(prev)*max_churn_pct)
    new (non-overlapping) pairs, by rank order. If min_persistence_refreshes >= 1 and conn/chain_id/ts_utc
    provided, keep prev pairs that have failed selection for fewer than K refreshes (sticky).
    """
    if max_churn_pct >= 1.0 or not prev_pairs:
        return new_pairs[:page_size]
    prev_addrs = {p.get("pair_address") for p in prev_pairs if p.get("pair_address")}
    new_addrs = {p.get("pair_address") for p in new_pairs if p.get("pair_address")}
    overlapping = prev_addrs & new_addrs
    sticky_addrs: set = set()
    if min_persistence_refreshes >= 1 and conn and chain_id and ts_utc:
        failure_counts = _load_persistence(conn, chain_id, prev_addrs)
        _update_persistence(conn, chain_id, ts_utc, prev_addrs, new_addrs, min_persistence_refreshes)
        sticky_addrs = {a for a in prev_addrs if failure_counts.get(a, 0) < min_persistence_refreshes and a not in new_addrs}
    keep_addrs = overlapping | sticky_addrs
    kept = [p for p in prev_pairs if p.get("pair_address") in keep_addrs]
    new_candidates = [p for p in new_pairs if p.get("pair_address") not in keep_addrs]
    max_replace = max(0, int(__import__("math").ceil(len(prev_pairs) * max_churn_pct)))
    slots = min(max_replace, page_size - len(kept))
    result = kept + new_candidates[:slots]
    return result[:page_size]


def _log_persistence_stats(
    conn: sqlite3.Connection,
    chain_id: str,
    prev_addrs: set,
    new_selected_addrs: set,
    result_addrs: set,
    min_k: int,
) -> None:
    """Log one compact line per refresh: overlap, kept_sticky, failures_incremented, removed_due_to_K, max_failure_streak_top3."""
    if min_k < 1 or not prev_addrs:
        return
    overlap_count = len(prev_addrs & new_selected_addrs)
    kept_sticky_count = len((result_addrs & prev_addrs) - new_selected_addrs)
    failures_incremented_count = len(prev_addrs - new_selected_addrs)
    removed_addrs = prev_addrs - result_addrs
    removed_due_to_persistence_count = 0
    if removed_addrs:
        try:
            placeholders = ",".join("?" for _ in removed_addrs)
            cur = conn.execute(
                f"SELECT COUNT(*) FROM universe_persistence WHERE chain_id = ? AND pair_address IN ({placeholders}) AND consecutive_failures >= ?",
                [chain_id] + list(removed_addrs) + [min_k],
            )
            removed_due_to_persistence_count = cur.fetchone()[0] or 0
        except sqlite3.OperationalError:
            pass
    max_failure_streak_top3: List[int] = []
    try:
        cur = conn.execute(
            "SELECT consecutive_failures FROM universe_persistence WHERE chain_id = ? ORDER BY consecutive_failures DESC LIMIT 3",
            (chain_id,),
        )
        max_failure_streak_top3 = [int(r[0]) for r in cur.fetchall() if r[0] is not None]
    except sqlite3.OperationalError:
        pass
    _log(
        f"[persistence] overlap={overlap_count} kept_sticky={kept_sticky_count} failures_inc={failures_incremented_count} removed_K={removed_due_to_persistence_count} max_streak_top3={max_failure_streak_top3}"
    )


def _persist_churn_log(
    conn: sqlite3.Connection,
    ts_utc: str,
    chain_id: str,
    removed: List[Tuple[str, str, Optional[float], Optional[float]]],
    added: List[Tuple[str, str, Optional[float], Optional[float]]],
) -> None:
    """Log removed (pair_address, reason, liq, vol) and added (pair_address, reason, liq, vol) for audit."""
    for pair_address, reason, liq, vol in removed:
        try:
            conn.execute(
                "INSERT OR REPLACE INTO universe_churn_log (ts_utc, chain_id, pair_address, action, reason, liquidity_usd, vol_h24) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ts_utc, chain_id, pair_address, "remove", (reason or "")[:200], liq, vol),
            )
        except sqlite3.OperationalError:
            pass
    for pair_address, reason, liq, vol in added:
        try:
            conn.execute(
                "INSERT OR REPLACE INTO universe_churn_log (ts_utc, chain_id, pair_address, action, reason, liquidity_usd, vol_h24) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ts_utc, chain_id, pair_address, "add", (reason or "")[:200], liq, vol),
            )
        except sqlite3.OperationalError:
            pass
    conn.commit()


def _persist_universe_allowlist(
    conn: sqlite3.Connection,
    ts_utc: str,
    pairs: List[Dict[str, Any]],
    source: str,
    query_summary: str,
    prev_addrs: Optional[set] = None,
    new_selected_addrs: Optional[set] = None,
) -> None:
    """Write one row per pair to universe_allowlist for audit trail; reason_added when columns exist."""
    result_addrs = {p.get("pair_address") for p in pairs if p.get("pair_address")}
    for p in pairs:
        addr = p.get("pair_address", "")
        if prev_addrs is not None and new_selected_addrs is not None:
            if addr in prev_addrs and addr in new_selected_addrs:
                reason_added = "overlap"
            elif addr in prev_addrs:
                reason_added = "sticky"
            else:
                reason_added = "churn_replace" if prev_addrs else source
        else:
            reason_added = source
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO universe_allowlist
                (ts_utc, chain_id, pair_address, label, liquidity_usd, vol_h24, source, query_summary, reason_added)
                VALUES (:ts_utc, :chain_id, :pair_address, :label, :liquidity_usd, :vol_h24, :source, :query_summary, :reason_added)
                """,
                {
                    "ts_utc": ts_utc,
                    "chain_id": p.get("chain_id", ""),
                    "pair_address": addr,
                    "label": p.get("label"),
                    "liquidity_usd": p.get("liquidity_usd"),
                    "vol_h24": p.get("vol_h24"),
                    "source": source,
                    "query_summary": (query_summary or "")[:500],
                    "reason_added": (reason_added or "")[:100],
                },
            )
        except sqlite3.OperationalError:
            conn.execute(
                """
                INSERT OR REPLACE INTO universe_allowlist
                (ts_utc, chain_id, pair_address, label, liquidity_usd, vol_h24, source, query_summary)
                VALUES (:ts_utc, :chain_id, :pair_address, :label, :liquidity_usd, :vol_h24, :source, :query_summary)
                """,
                {
                    "ts_utc": ts_utc,
                    "chain_id": p.get("chain_id", ""),
                    "pair_address": addr,
                    "label": p.get("label"),
                    "liquidity_usd": p.get("liquidity_usd"),
                    "vol_h24": p.get("vol_h24"),
                    "source": source,
                    "query_summary": (query_summary or "")[:500],
                },
            )
    conn.commit()


def fetch_dex_search_pairs(query: str) -> List[Dict[str, Any]]:
    """
    Call GET /latest/dex/search?q=<query> with 429 retry.
    Returns list of raw pair dicts from response (empty on failure).
    """
    url = f"{DEX_BASE_URL}/latest/dex/search?q={query}"
    try:
        r = requests.get(url, timeout=HTTP_TIMEOUT_S)
        if r.status_code == 429:
            time.sleep(2.0)
            r = requests.get(url, timeout=HTTP_TIMEOUT_S)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []
    pairs_raw = data.get("pairs") if isinstance(data, dict) else None
    if not isinstance(pairs_raw, list):
        return []
    return [x for x in pairs_raw if isinstance(x, dict)]


def fetch_dex_universe_top_pairs(
    chain_id: str = "solana",
    page_size: int = 50,
    min_liquidity_usd: float = 250_000,
    min_vol_h24: float = 500_000,
    quote_allowlist: Optional[List[str]] = None,
    reject_same_symbol: bool = True,
    reject_stable_stable: bool = True,
    queries: Optional[List[str]] = None,
    universe_debug: int = 0,
) -> List[Dict[str, str]]:
    """
    Fetch top DEX pairs for a chain via Dexscreener search API (multiple queries, merged).
    Uses pairAddress only (not dexId). De-duplicates by pairAddress across queries, then
    applies quality gates. Returns list of {chain_id, pair_address, label}.
    """
    allowlist = quote_allowlist if quote_allowlist is not None else ["USDC", "USDT"]
    chain_lower = chain_id.lower()
    if queries is None or len(queries) == 0:
        queries = DEFAULT_UNIVERSE_QUERIES_BY_CHAIN.get(chain_lower, ["USDC", "USDT", "SOL"])

    if universe_debug > 0:
        _log(f"[universe] chain={chain_id} queries={queries}")

    # Per-query fetch and merge; de-dup by pairAddress (first wins)
    all_items: List[Dict[str, Any]] = []
    seen_addr: set = set()
    for q in queries:
        raw = fetch_dex_search_pairs(q)
        chain_for_q = [item for item in raw if (item.get("chainId") or "").strip().lower() == chain_lower]
        if universe_debug > 0:
            _log(f"[universe] q={q} candidates={len(chain_for_q)}")
        for item in chain_for_q:
            addr = (item.get("pairAddress") or "").strip()
            if not addr or addr in seen_addr:
                continue
            seen_addr.add(addr)
            all_items.append(item)

    merged_count = len(all_items)
    if universe_debug > 0:
        _log(f"[universe] merged unique candidates={merged_count}")

    out: List[Dict[str, Any]] = []
    seen: set = set()
    debug_count = 0
    for item in all_items:
        addr = (item.get("pairAddress") or "").strip()
        if not addr or addr in seen:
            continue
        base = (safe_get(item, "baseToken.symbol") or "").strip().upper() or "?"
        quote = (safe_get(item, "quoteToken.symbol") or "").strip().upper() or "?"
        label = f"{base}/{quote}" if (base != "?" and quote != "?") else f"{chain_id}/{addr[:8]}"
        liq = to_float(safe_get(item, "liquidity.usd"))
        vol = to_float(safe_get(item, "volume.h24"))

        keep, reason = _universe_keep_pair(
            item,
            min_liquidity_usd=min_liquidity_usd,
            min_vol_h24=min_vol_h24,
            quote_allowlist=allowlist,
            reject_same_symbol=reject_same_symbol,
            reject_stable_stable=reject_stable_stable,
        )
        if universe_debug > 0 and debug_count < universe_debug:
            status = "[OK] accept" if keep else f"[REJECT] {reason}"
            _log(f"[universe] {label} {addr[:8]} liq={_fmt_millions(liq)} vol24={_fmt_millions(vol)} {status}")
            debug_count += 1
        if not keep:
            continue
        seen.add(addr)
        out.append({
            "chain_id": chain_id,
            "pair_address": addr,
            "label": label,
            "liquidity_usd": liq,
            "vol_h24": vol,
        })
    # Deterministic selection: sort by liq desc, vol desc, label asc, pair_address asc; then take page_size
    out.sort(key=_universe_rank_key)
    out = out[:page_size]

    if universe_debug > 0:
        _log(f"[universe] accepted count={len(out)}")
        top_labels = [p["label"] for p in out[:5]]
        _log(f"[universe] top 5 accepted: {top_labels}")

    return out


def load_universe_config(config_path: str) -> Dict[str, Any]:
    """Load universe section from config YAML. Includes queries, bootstrap_pairs, max_churn_pct, etc."""
    path = Path(config_path)
    defaults = {
        "enabled": False,
        "chain_id": "solana",
        "page_size": 50,
        "refresh_minutes": 60,
        "min_liquidity_usd": 250_000,
        "min_vol_h24": 500_000,
        "quote_allowlist": ["USDC", "USDT"],
        "reject_same_symbol": True,
        "reject_stable_stable": True,
        "queries": ["USDC", "USDT", "SOL", "SOL/USDC", "orca"],
        "max_churn_pct": 0.20,
        "min_persistence_refreshes": 2,
        "bootstrap_pairs": None,
    }
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
    out = {**defaults}
    for k in list(out.keys()):
        if k in u and u[k] is not None:
            out[k] = u[k]
    if isinstance(out.get("quote_allowlist"), list):
        out["quote_allowlist"] = [str(s).strip() for s in out["quote_allowlist"] if s]
    if isinstance(out.get("queries"), list):
        out["queries"] = [str(s).strip() for s in out["queries"] if s]
    if out.get("max_churn_pct") is not None:
        try:
            out["max_churn_pct"] = float(out["max_churn_pct"])
        except (TypeError, ValueError):
            out["max_churn_pct"] = 0.20
    if out.get("min_persistence_refreshes") is not None:
        try:
            out["min_persistence_refreshes"] = max(0, int(out["min_persistence_refreshes"]))
        except (TypeError, ValueError):
            out["min_persistence_refreshes"] = 2
    return out


def load_bootstrap_pairs_from_config(config_path: str, chain_id: str) -> List[Dict[str, Any]]:
    """Load universe.bootstrap_pairs from config; return only items matching chain_id (each: chain_id, pair_address, label)."""
    path = Path(config_path)
    if not path.exists():
        return []
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return []
    u = (data or {}).get("universe") or {}
    raw = u.get("bootstrap_pairs")
    if not isinstance(raw, list):
        return []
    chain_lower = chain_id.lower()
    out: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        cid = (item.get("chain_id") or item.get("chainId") or "").strip().lower()
        if cid != chain_lower:
            continue
        addr = (item.get("pair_address") or item.get("pairAddress") or "").strip()
        if not addr:
            continue
        out.append({
            "chain_id": chain_id,
            "pair_address": addr,
            "label": str(item.get("label", "")).strip() or f"{chain_id}/{addr[:8]}",
            "liquidity_usd": None,
            "vol_h24": None,
        })
    return out


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
    if sys.prefix == sys.base_prefix:
        print("Not running inside venv. Use .\\scripts\\run.ps1 poll (or universe-poll) or .\\.venv\\Scripts\\python.exe ...", flush=True)
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
    parser.add_argument("--universe-debug", type=int, default=0, metavar="N", help="Print first N universe candidates with accept/reject reasons (default: 0)")
    parser.add_argument("--universe-quote-allowlist", default=None, metavar="CSV", help='Quote token allowlist e.g. "USDC,USDT" (overrides config)')
    parser.add_argument("--universe-reject-stable-stable", dest="universe_reject_stable_stable", action="store_true", default=None, help="Reject stable/stable pairs (default from config)")
    parser.add_argument("--no-universe-reject-stable-stable", dest="universe_reject_stable_stable", action="store_false", help="Allow stable/stable pairs")
    parser.add_argument("--universe-reject-same-symbol", dest="universe_reject_same_symbol", action="store_true", default=None, help="Reject base==quote (default from config)")
    parser.add_argument("--no-universe-reject-same-symbol", dest="universe_reject_same_symbol", action="store_false", help="Allow same base/quote")
    parser.add_argument("--universe-query", dest="universe_query", action="append", default=None, metavar="Q", help="Search query for universe (repeatable); e.g. USDC, USDT. Overrides config queries.")
    parser.add_argument("--universe-max-churn-pct", dest="universe_max_churn_pct", type=float, default=None, metavar="PCT", help="Max fraction of allowlist replaceable per refresh (0-1; default from config 0.20; 1.0 = no churn limit)")
    parser.add_argument("--universe-min-persistence-refreshes", dest="universe_min_persistence_refreshes", type=int, default=None, metavar="K", help="Require pair to fail selection K refreshes before removal (default from config 2; 0 = disable)")
    args = parser.parse_args()
    interval_sec = args.interval

    # Universe mode: refresh allowlist periodically (--universe or --universe top)
    universe_enabled = (getattr(args, "universe", None) == "top")
    universe_refresh_sec = max(60, float(getattr(args, "universe_refresh_minutes", 60)) * 60)
    universe_last_refresh: List[Optional[float]] = [None]
    universe_cache: List[Optional[List[Dict[str, Any]]]] = [None]
    universe_prev_pairs: List[Optional[List[Dict[str, Any]]]] = [None]

    def _get_universe_pairs(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        if not universe_enabled:
            return []
        now = time.time()
        if universe_last_refresh[0] is None or (now - universe_last_refresh[0]) >= universe_refresh_sec:
            import math
            cfg = load_universe_config(args.config)
            chain = getattr(args, "universe_chain", "solana") or cfg.get("chain_id", "solana")
            page_size = getattr(args, "universe_page_size", None) or cfg.get("page_size", 50)
            min_liq = getattr(args, "universe_min_liquidity", None) or cfg.get("min_liquidity_usd", 250_000)
            min_vol = getattr(args, "universe_min_vol_h24", None) or cfg.get("min_vol_h24", 500_000)
            quote_allowlist_cfg = cfg.get("quote_allowlist") or ["USDC", "USDT"]
            if getattr(args, "universe_quote_allowlist", None) and str(args.universe_quote_allowlist).strip():
                quote_allowlist = [s.strip() for s in str(args.universe_quote_allowlist).split(",") if s.strip()]
            else:
                quote_allowlist = quote_allowlist_cfg
            reject_stable = cfg.get("reject_stable_stable", True) if getattr(args, "universe_reject_stable_stable", None) is None else args.universe_reject_stable_stable
            reject_same = cfg.get("reject_same_symbol", True) if getattr(args, "universe_reject_same_symbol", None) is None else args.universe_reject_same_symbol
            debug_n = getattr(args, "universe_debug", 0) or 0
            cli_queries = getattr(args, "universe_query", None) or []
            if cli_queries:
                queries = [str(q).strip() for q in cli_queries if str(q).strip()]
            else:
                queries = cfg.get("queries") or None
            max_churn_pct = getattr(args, "universe_max_churn_pct", None)
            if max_churn_pct is None:
                max_churn_pct = float(cfg.get("max_churn_pct", 0.20))
            min_persistence_refreshes = getattr(args, "universe_min_persistence_refreshes", None)
            if min_persistence_refreshes is None:
                min_persistence_refreshes = int(cfg.get("min_persistence_refreshes", 2))
            query_summary = ",".join(queries) if queries else "CLI override"

            pairs = fetch_dex_universe_top_pairs(
                chain_id=chain,
                page_size=page_size,
                min_liquidity_usd=min_liq,
                min_vol_h24=min_vol,
                quote_allowlist=quote_allowlist,
                reject_same_symbol=reject_same,
                reject_stable_stable=reject_stable,
                queries=queries,
                universe_debug=debug_n,
            )
            source = "universe"
            if len(pairs) == 0:
                _log("Universe empty after filters; attempting relaxed thresholds within guardrails...")
                relaxed_liq = max(0.0, min_liq * 0.25)
                relaxed_vol = max(0.0, min_vol * 0.25)
                pairs = fetch_dex_universe_top_pairs(
                    chain_id=chain,
                    page_size=page_size,
                    min_liquidity_usd=relaxed_liq,
                    min_vol_h24=relaxed_vol,
                    quote_allowlist=quote_allowlist,
                    reject_same_symbol=reject_same,
                    reject_stable_stable=reject_stable,
                    queries=queries,
                    universe_debug=debug_n,
                )
                source = "relaxed"
            if len(pairs) == 0:
                bootstrap = load_bootstrap_pairs_from_config(args.config, chain)
                if bootstrap:
                    pairs = bootstrap
                    source = "bootstrap_pairs"
                    _log("Fallback used: bootstrap_pairs (from config universe.bootstrap_pairs)")
                else:
                    pairs_raw = load_dex_pairs_from_config(args.config)
                    pairs = [{"chain_id": p["chain_id"], "pair_address": p["pair_address"], "label": p["label"], "liquidity_usd": None, "vol_h24": None} for p in pairs_raw]
                    source = "config_fallback"
                    _log("Fallback used: config_fallback (configured pairs)")
            prev = universe_prev_pairs[0] or []
            ts = utc_now_iso()
            new_selected_addrs = {p.get("pair_address") for p in pairs if p.get("pair_address")}
            result = _apply_churn_control(
                prev, pairs, page_size, max_churn_pct,
                conn=conn, chain_id=chain, ts_utc=ts,
                min_persistence_refreshes=min_persistence_refreshes,
            )
            prev_addrs = {p.get("pair_address") for p in prev if p.get("pair_address")}
            result_addrs = {p.get("pair_address") for p in result if p.get("pair_address")}
            if prev and result:
                kept = len(prev_addrs & result_addrs)
                replaced = len(result_addrs - prev_addrs)
                max_allowed = math.ceil(len(prev) * max_churn_pct)
                _log(f"Universe churn: kept={kept} replaced={replaced} max_allowed={max_allowed}")
            removed_addrs = prev_addrs - result_addrs
            added_addrs = result_addrs - prev_addrs
            prev_by_addr = {p.get("pair_address"): p for p in prev if p.get("pair_address")}
            result_by_addr = {p.get("pair_address"): p for p in result if p.get("pair_address")}
            removed_log = [(a, "churn_evicted", prev_by_addr.get(a, {}).get("liquidity_usd"), prev_by_addr.get(a, {}).get("vol_h24")) for a in removed_addrs]
            added_log = [(a, "churn_replace" if prev_addrs else source, result_by_addr.get(a, {}).get("liquidity_usd"), result_by_addr.get(a, {}).get("vol_h24")) for a in added_addrs]
            _persist_churn_log(conn, ts, chain, removed_log, added_log)
            _log_persistence_stats(conn, chain, prev_addrs, new_selected_addrs, result_addrs, min_persistence_refreshes)
            universe_prev_pairs[0] = result
            universe_cache[0] = result
            universe_last_refresh[0] = now
            _persist_universe_allowlist(conn, ts, result, source, query_summary, prev_addrs=prev_addrs, new_selected_addrs=new_selected_addrs)
            allowlist_str = "/".join(quote_allowlist) if quote_allowlist else "none"
            _log(f"Universe refreshed: {len(result)} pairs (chain={chain}, allowlist={allowlist_str})")
            _log("Top 5 selected universe pairs (label, address):")
            for i, p in enumerate(result[:5], 1):
                _log(f"  {i}. {p.get('label', '?')}  {p.get('pair_address', '')}")
        return universe_cache[0] or []

    conn = sqlite3.connect(DB_PATH)
    ensure_db(conn)

    # Build dex_pairs list (universe mode needs conn for persist + churn)
    dex_pairs: List[Dict[str, Any]] = []
    if universe_enabled:
        dex_pairs = _get_universe_pairs(conn)
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
                u = _get_universe_pairs(conn)
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
