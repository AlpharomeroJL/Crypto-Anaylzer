"""
Public Advanced Trade REST (no API keys): products list and product candles.

See CDP: GET /api/v3/brokerage/market/products and
GET /api/v3/brokerage/market/products/{product_id}/candles
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode

import requests

COINBASE_ADVANCED_REST_BASE = "https://api.coinbase.com"
PUBLIC_PRODUCTS_PATH = "/api/v3/brokerage/market/products"
# Max candles per request (API default/max 350 for public candles).
MAX_CANDLES_PER_REQUEST = 350
HTTP_TIMEOUT_S = 45.0


@dataclass(frozen=True)
class CandleRow:
    """One OHLCV bucket; start_unix is bar open (UTC epoch seconds)."""

    start_unix: int
    open: float
    high: float
    low: float
    close: float
    volume: float


def _float(x: Any) -> float:
    if x is None:
        return float("nan")
    return float(str(x))


class CoinbaseAdvancedRestClient:
    """Thin client for Coinbase Advanced Trade public market REST."""

    def __init__(
        self,
        base_url: str = COINBASE_ADVANCED_REST_BASE,
        session: Optional[requests.Session] = None,
        timeout_s: float = HTTP_TIMEOUT_S,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._session = session or requests.Session()
        self._timeout = timeout_s

    def list_public_products(
        self,
        *,
        limit: Optional[int] = None,
        product_ids: Optional[List[str]] = None,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """GET /api/v3/brokerage/market/products."""
        url = f"{self._base}{PUBLIC_PRODUCTS_PATH}"
        params: List[tuple[str, Any]] = []
        if limit is not None:
            params.append(("limit", limit))
        if cursor:
            params.append(("cursor", cursor))
        if product_ids:
            for pid in product_ids:
                params.append(("product_ids", pid))

        qs = urlencode(params) if params else ""
        full = f"{url}?{qs}" if qs else url
        r = self._session.get(full, timeout=self._timeout)
        r.raise_for_status()
        return r.json()

    def get_public_candles(
        self,
        product_id: str,
        *,
        start_sec: int,
        end_sec: int,
        granularity: str = "ONE_HOUR",
    ) -> List[CandleRow]:
        """
        GET .../market/products/{product_id}/candles

        start_sec / end_sec: Unix seconds (inclusive window per request).
        """
        path = f"/api/v3/brokerage/market/products/{quote(product_id, safe='')}/candles"
        url = f"{self._base}{path}"
        params = {
            "start": str(start_sec),
            "end": str(end_sec),
            "granularity": granularity,
        }
        r = self._session.get(url, params=params, timeout=self._timeout)
        r.raise_for_status()
        data = r.json()
        candles = data.get("candles") or []
        out: List[CandleRow] = []
        for c in candles:
            su = int(str(c.get("start", "0")))
            out.append(
                CandleRow(
                    start_unix=su,
                    open=_float(c.get("open")),
                    high=_float(c.get("high")),
                    low=_float(c.get("low")),
                    close=_float(c.get("close")),
                    volume=_float(c.get("volume")),
                )
            )
        return out

    def iter_public_candles_1h(
        self,
        product_id: str,
        *,
        start_sec: int,
        end_sec: int,
    ) -> List[CandleRow]:
        """
        Paginate candle requests: at most 350 hourly buckets per call.
        """
        if end_sec <= start_sec:
            return []
        all_rows: List[CandleRow] = []
        span = MAX_CANDLES_PER_REQUEST * 3600
        cur = start_sec
        while cur < end_sec:
            nxt = min(cur + span, end_sec)
            chunk = self.get_public_candles(
                product_id,
                start_sec=cur,
                end_sec=nxt,
                granularity="ONE_HOUR",
            )
            all_rows.extend(chunk)
            cur = nxt
        return all_rows
