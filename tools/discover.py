#!/usr/bin/env python3
"""
Dexscreener discovery (SOL/USDC on Solana).

Default behavior:
- Searches Dexscreener
- Filters to chainId=solana, base=SOL, quote=USDC
- Ranks by liquidity/volume/txns
- Prints the best pair to use for polling later

Usage:
  python dex_discover.py "SOL/USDC"
  python dex_discover.py "SOL USDC" --top 15
  python dex_discover.py "SOL/USDC" --json
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any, Dict, List, Optional

import requests

BASE_URL = "https://api.dexscreener.com"


def _safe_get(d: Dict[str, Any], path: str, default: Any = None) -> Any:
    cur: Any = d
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _to_float(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def search_pairs(query: str, timeout_s: float = 15.0, retries: int = 3) -> List[Dict[str, Any]]:
    url = f"{BASE_URL}/latest/dex/search"
    params = {"q": query}

    last_err: Optional[str] = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout_s)
            if resp.status_code == 429:
                wait_s = 1.5 * attempt
                time.sleep(wait_s)
                last_err = f"Rate limited (HTTP 429). Waited {wait_s:.1f}s."
                continue
            resp.raise_for_status()
            data = resp.json()
            pairs = data.get("pairs") or []
            if not isinstance(pairs, list):
                raise RuntimeError("Unexpected response: 'pairs' is not a list.")
            return pairs
        except (requests.RequestException, ValueError, RuntimeError) as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(0.5 * attempt)

    raise RuntimeError(f"Failed after {retries} tries. Last error: {last_err}")


def is_sol_usdc_solana(p: Dict[str, Any]) -> bool:
    chain_ok = str(p.get("chainId", "")).lower() == "solana"

    base_sym = str(_safe_get(p, "baseToken.symbol", "")).upper()
    quote_sym = str(_safe_get(p, "quoteToken.symbol", "")).upper()

    base_ok = "SOL" in base_sym
    quote_ok = "USDC" in quote_sym

    return chain_ok and base_ok and quote_ok


def score_pair(p: Dict[str, Any]) -> float:
    # Prefer high liquidity + high volume + active txns
    liq = _to_float(_safe_get(p, "liquidity.usd", 0.0))
    vol24 = _to_float(_safe_get(p, "volume.h24", 0.0))
    buys24 = _to_float(_safe_get(p, "txns.h24.buys", 0.0))
    sells24 = _to_float(_safe_get(p, "txns.h24.sells", 0.0))
    txns24 = buys24 + sells24

    return liq * 1.0 + vol24 * 0.25 + txns24 * 10.0


def fmt_num(x: Any) -> str:
    if x is None:
        return "-"
    try:
        xf = float(x)
    except Exception:
        return str(x)
    if abs(xf) >= 1_000_000:
        return f"{xf/1_000_000:.2f}M"
    if abs(xf) >= 1_000:
        return f"{xf/1_000:.2f}K"
    if abs(xf) >= 1:
        return f"{xf:.6g}"
    return f"{xf:.8f}"


def format_pair_row(p: Dict[str, Any], idx: int) -> str:
    chain_id = p.get("chainId", "")
    dex_id = p.get("dexId", "")
    pair_address = p.get("pairAddress", "")
    price_usd = p.get("priceUsd", None)
    liq_usd = _safe_get(p, "liquidity.usd", None)
    vol24 = _safe_get(p, "volume.h24", None)
    buys24 = _safe_get(p, "txns.h24.buys", None)
    sells24 = _safe_get(p, "txns.h24.sells", None)

    return (
        f"[{idx:02d}] {chain_id:<8} {dex_id:<10} SOL/USDC  "
        f"price=${fmt_num(price_usd):<12} liq=${fmt_num(liq_usd):<10} "
        f"vol24=${fmt_num(vol24):<10} txns24={buys24 if buys24 is not None else '-'}"
        f"/{sells24 if sells24 is not None else '-'}  pair={pair_address}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Discover SOL/USDC on Solana via Dexscreener")
    ap.add_argument("query", help='Search query (e.g. "SOL/USDC", "SOL USDC")')
    ap.add_argument("--top", type=int, default=10, help="How many filtered results to show (default: 10)")
    ap.add_argument("--json", action="store_true", help="Print raw JSON for the filtered pairs")
    args = ap.parse_args()

    pairs = search_pairs(args.query)

    filtered = [p for p in pairs if is_sol_usdc_solana(p)]
    if not filtered:
        print("No SOL/USDC pairs found on Solana from this search.")
        print("Tip: try a broader query like: python dex_discover.py \"SOL USDC\"")
        return 0

    ranked = sorted(filtered, key=score_pair, reverse=True)
    shown = ranked[: max(1, args.top)]

    print(f"Found {len(pairs)} pairs. Filtered to {len(filtered)} SOL/USDC pairs on Solana.")
    print(f"Showing top {len(shown)} (ranked):\n")

    if args.json:
        print(json.dumps(shown, indent=2))
        return 0

    for i, p in enumerate(shown, start=1):
        print(format_pair_row(p, i))

    best = ranked[0]
    print("\nBEST MATCH to track (use these for polling):")
    print("  chainId     =", best.get("chainId"))
    print("  pairAddress =", best.get("pairAddress"))
    print("Example poll endpoint: /latest/dex/pairs/{chainId}/{pairAddress}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
