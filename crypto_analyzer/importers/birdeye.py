"""
Birdeye API client and response mapping for historical pool data.

All field-name assumptions for Birdeye responses live in this module.
Paste a real Birdeye response into the JSON example block below and update
parse_hourly_point / items_from_response to match.

Many Birdeye OHLCV responses do not include liquidity_usd or true 24h volume;
liquidity_usd may be null and vol_h24 may be per-candle only. To fix: set
vol_h24 to a rolling 24h sum of hourly volume here if needed; leave
liquidity_usd null or add a liquidity endpoint. See docs/birdeye_import.md
(Two gotchas).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# --- Endpoint configuration (update if Birdeye changes) ---
BIRDEYE_BASE_URL = "https://public-api.birdeye.so"
OHLCV_PAIR_PATH = "/defi/ohlcv/pair"
# Optional: historical liquidity endpoint if available later
# LIQUIDITY_PAIR_PATH = "/defi/..."

# --- Response shape (Birdeye pair OHLCV). Update keys to match real payload. ---
# Top-level: success, data
# data.items[]: each candle
# Candle keys used below: unixTime (or unix_time), c (close price), v (volume), etc.
# If your response uses different names, change ONLY the constants and parse_* below.


# JSON example (paste actual Birdeye response here and align mapping):
#
# {
#   "success": true,
#   "data": {
#     "items": [
#       {
#         "address": "Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE",
#         "o": 131.51,
#         "h": 132.23,
#         "l": 131.51,
#         "c": 131.98,
#         "v": 6156.15,
#         "type": "15m",
#         "unixTime": 1726700400
#       }
#     ]
#   }
# }
#
# Pair OHLCV does not include liquidity_usd; set to None in parse_hourly_point.
# For vol_h24: we use per-candle v as the period volume; caller may aggregate to 24h.


def parse_hourly_point(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map one Birdeye OHLCV candle (item) to a normalized snapshot point.

    All Birdeye field names are isolated here. Returns dict with keys:
    ts_utc (str ISO), liquidity_usd (float or None), vol_h24 (float or None), price (float).
    """
    # Timestamp: Birdeye uses unixTime (seconds). Store as UTC ISO.
    unix_ts = item.get("unixTime") or item.get("unix_time")
    if unix_ts is None:
        raise ValueError("Missing unixTime / unix_time in Birdeye item")
    ts_utc = _unix_to_iso_utc(int(unix_ts))

    # Price: use close (c); fallback to mid (o+l)/2 or o
    c = item.get("c")
    if c is not None:
        price = float(c)
    else:
        o, l_ = item.get("o"), item.get("l")
        if o is not None and l_ is not None:
            price = (float(o) + float(l_)) / 2.0
        else:
            price = float(o) if o is not None else 0.0

    # Volume: per-candle v (optional). Caller can aggregate to 24h.
    v = item.get("v") or item.get("v_usd")
    vol_h24 = float(v) if v is not None else None

    # Liquidity: pair OHLCV endpoint typically does not provide it.
    liquidity_usd = item.get("liquidity_usd")
    if liquidity_usd is not None:
        liquidity_usd = float(liquidity_usd)
    else:
        liquidity_usd = None

    return {
        "ts_utc": ts_utc,
        "liquidity_usd": liquidity_usd,
        "vol_h24": vol_h24,
        "price": price,
    }


def _unix_to_iso_utc(unix_sec: int) -> str:
    """Convert Unix timestamp (seconds) to UTC ISO string."""
    from datetime import datetime, timezone

    return datetime.fromtimestamp(unix_sec, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def items_from_response(response_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract list of candle items from Birdeye API response.
    All response field names are isolated here.
    """
    if not response_json.get("success"):
        return []
    data = response_json.get("data") or {}
    items = data.get("items") or data.get("data") or []
    return list(items) if isinstance(items, list) else []


class BirdeyeClient:
    """
    Birdeye API client with rate limiting and retry on 429/5xx.
    """

    def __init__(
        self,
        api_token: str,
        base_url: str = BIRDEYE_BASE_URL,
        rate_limit_qps: float = 2.0,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
    ):
        self.api_token = api_token
        self.base_url = base_url.rstrip("/")
        self.rate_limit_qps = max(0.1, rate_limit_qps)
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self._last_request_time: float = 0.0

    def _wait_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        min_interval = 1.0 / self.rate_limit_qps
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.monotonic()

    def _request(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        url = self.base_url + path
        headers = {"X-API-KEY": self.api_token}
        if extra_headers:
            headers.update(extra_headers)
        for attempt in range(self.max_retries + 1):
            self._wait_rate_limit()
            try:
                resp = requests.get(
                    url,
                    params=params or {},
                    headers=headers,
                    timeout=30,
                )
            except requests.RequestException as e:
                logger.warning("Birdeye request error (attempt %s): %s", attempt + 1, e)
                if attempt == self.max_retries:
                    raise
                time.sleep(self.backoff_factor ** attempt)
                continue
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 60))
                logger.warning("Birdeye 429; sleeping %s s", retry_after)
                time.sleep(min(retry_after, 120))
                continue
            if resp.status_code >= 500:
                logger.warning("Birdeye %s (attempt %s)", resp.status_code, attempt + 1)
                if attempt == self.max_retries:
                    resp.raise_for_status()
                time.sleep(self.backoff_factor ** attempt)
                continue
            resp.raise_for_status()
            return resp.json()
        return {}

    def fetch_ohlcv_pair(
        self,
        chain: str,
        pair_address: str,
        interval: str,
        time_from: int,
        time_to: int,
    ) -> List[Dict[str, Any]]:
        """
        Fetch OHLCV for a pair. Returns list of raw item dicts (use parse_hourly_point per item).
        """
        params = {
            "address": pair_address,
            "type": interval,
            "time_from": time_from,
            "time_to": time_to,
        }
        extra_headers = {"x-chain": chain.lower()}
        data = self._request(OHLCV_PAIR_PATH, params=params, extra_headers=extra_headers)
        return items_from_response(data)
