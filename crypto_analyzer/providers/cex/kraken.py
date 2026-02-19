"""
Kraken spot price provider.

Uses the public Kraken API (no authentication required):
  GET https://api.kraken.com/0/public/Ticker?pair={pair}
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from ..base import ProviderStatus, SpotQuote

KRAKEN_BASE_URL = "https://api.kraken.com"
HTTP_TIMEOUT_S = 15.0

_SYMBOL_TO_PAIR = {
    "SOL": "SOLUSD",
    "ETH": "ETHUSD",
    "BTC": "XBTUSD",
}


class KrakenSpotProvider:
    """Fetch spot prices from the Kraken public API."""

    @property
    def provider_name(self) -> str:
        return "kraken"

    def get_spot(self, symbol: str) -> SpotQuote:
        pair = _SYMBOL_TO_PAIR.get(symbol.upper(), f"{symbol.upper()}USD")
        url = f"{KRAKEN_BASE_URL}/0/public/Ticker"
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

        resp = requests.get(url, params={"pair": pair}, timeout=HTTP_TIMEOUT_S)
        if resp.status_code == 429:
            raise RuntimeError("Kraken rate limit (HTTP 429)")
        resp.raise_for_status()

        data = resp.json()
        if data.get("error"):
            raise RuntimeError(f"Kraken error: {data['error']}")

        result = data.get("result", {})
        if not result:
            raise RuntimeError("Kraken response missing result")

        first_key = next(iter(result.keys()))
        last_trade = result[first_key].get("c", [None])
        if not last_trade or last_trade[0] is None:
            raise RuntimeError("Kraken response missing last trade price")

        price = float(last_trade[0])
        if price <= 0:
            return SpotQuote(
                symbol=symbol.upper(),
                price_usd=price,
                provider_name=self.provider_name,
                fetched_at_utc=ts,
                status=ProviderStatus.DEGRADED,
                error_message="Non-positive price",
            )

        return SpotQuote(
            symbol=symbol.upper(),
            price_usd=price,
            provider_name=self.provider_name,
            fetched_at_utc=ts,
        )
