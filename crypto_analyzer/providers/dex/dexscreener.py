"""
Dexscreener DEX snapshot provider.

Uses the public Dexscreener API (no authentication required):
  GET https://api.dexscreener.com/latest/dex/pairs/{chain}/{address}
  GET https://api.dexscreener.com/latest/dex/search?q={query}
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from ..base import DexSnapshot

DEX_BASE_URL = "https://api.dexscreener.com"
HTTP_TIMEOUT_S = 15.0


def _safe_get(d: Dict[str, Any], path: str, default: Any = None) -> Any:
    cur: Any = d
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _to_int(x: Any) -> Optional[int]:
    if x is None:
        return None
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _pick_pair_from_payload(data: dict) -> Dict[str, Any]:
    """Extract the first pair dict from various Dexscreener response shapes."""
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected Dex response type: {type(data)}")

    p = data.get("pair")
    if isinstance(p, dict):
        return p
    if isinstance(p, list) and p and isinstance(p[0], dict):
        return p[0]

    pairs = data.get("pairs")
    if isinstance(pairs, dict):
        return pairs
    if isinstance(pairs, list):
        for item in pairs:
            if isinstance(item, dict):
                return item

    if data.get("chainId") and (
        data.get("priceUsd") is not None or data.get("liquidity")
    ):
        return data

    if data.get("pair") is None and data.get("pairs") is None:
        raise RuntimeError(
            "Dex returned no data for this pair (may be delisted or invalid)."
        )
    raise RuntimeError(
        f"Unexpected Dex response shape. Keys: {list(data.keys())}"
    )


class DexscreenerDexProvider:
    """Fetch DEX pair snapshots from the Dexscreener public API."""

    @property
    def provider_name(self) -> str:
        return "dexscreener"

    def get_snapshot(self, chain_id: str, pair_address: str) -> DexSnapshot:
        url = f"{DEX_BASE_URL}/latest/dex/pairs/{chain_id}/{pair_address}"
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

        resp = requests.get(url, timeout=HTTP_TIMEOUT_S)
        if resp.status_code == 429:
            raise RuntimeError("Dexscreener rate limit (HTTP 429)")
        resp.raise_for_status()

        data = resp.json()

        if isinstance(data, dict) and (data.get("error") or data.get("message")):
            err = data.get("error") or data.get("message")
            raise RuntimeError(f"Dex API error: {err}")

        if isinstance(data, list) and data and isinstance(data[0], dict):
            pair = data[0]
        elif isinstance(data, dict):
            pair = _pick_pair_from_payload(data)
        else:
            raise RuntimeError(f"Unexpected Dex response type: {type(data)}")

        return DexSnapshot(
            chain_id=chain_id,
            pair_address=pair_address,
            dex_id=pair.get("dexId"),
            base_symbol=_safe_get(pair, "baseToken.symbol"),
            quote_symbol=_safe_get(pair, "quoteToken.symbol"),
            dex_price_usd=_to_float(pair.get("priceUsd")),
            dex_price_native=_to_float(pair.get("priceNative")),
            liquidity_usd=_to_float(_safe_get(pair, "liquidity.usd")),
            vol_h24=_to_float(_safe_get(pair, "volume.h24")),
            txns_h24_buys=_to_int(_safe_get(pair, "txns.h24.buys")),
            txns_h24_sells=_to_int(_safe_get(pair, "txns.h24.sells")),
            provider_name=self.provider_name,
            fetched_at_utc=ts,
            raw_json=json.dumps(pair, separators=(",", ":"), ensure_ascii=False),
        )

    def search_pairs(
        self, query: str, chain_id: str = "solana"
    ) -> List[Dict[str, Any]]:
        url = f"{DEX_BASE_URL}/latest/dex/search?q={query}"
        try:
            resp = requests.get(url, timeout=HTTP_TIMEOUT_S)
            if resp.status_code == 429:
                import time
                time.sleep(2.0)
                resp = requests.get(url, timeout=HTTP_TIMEOUT_S)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return []

        pairs_raw = data.get("pairs") if isinstance(data, dict) else None
        if not isinstance(pairs_raw, list):
            return []

        chain_lower = chain_id.lower()
        return [
            x for x in pairs_raw
            if isinstance(x, dict)
            and (x.get("chainId") or "").strip().lower() == chain_lower
        ]
