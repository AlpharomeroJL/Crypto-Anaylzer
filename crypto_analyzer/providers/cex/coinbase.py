"""
Coinbase spot price provider.

Uses the public Coinbase API (no authentication required):
  GET https://api.coinbase.com/v2/prices/{symbol}-USD/spot
"""
from __future__ import annotations

from datetime import datetime, timezone

import requests

from ..base import ProviderStatus, SpotQuote

COINBASE_BASE_URL = "https://api.coinbase.com"
HTTP_TIMEOUT_S = 15.0

_SYMBOL_TO_PRODUCT = {
    "SOL": "SOL-USD",
    "ETH": "ETH-USD",
    "BTC": "BTC-USD",
}


class CoinbaseSpotProvider:
    """Fetch spot prices from the Coinbase public API."""

    @property
    def provider_name(self) -> str:
        return "coinbase"

    def get_spot(self, symbol: str) -> SpotQuote:
        product = _SYMBOL_TO_PRODUCT.get(symbol.upper(), f"{symbol.upper()}-USD")
        url = f"{COINBASE_BASE_URL}/v2/prices/{product}/spot"
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

        resp = requests.get(url, timeout=HTTP_TIMEOUT_S)
        if resp.status_code == 429:
            raise RuntimeError("Coinbase rate limit (HTTP 429)")
        resp.raise_for_status()

        data = resp.json()
        amount = data.get("data", {}).get("amount")
        if amount is None:
            raise RuntimeError("Coinbase response missing data.amount")

        price = float(amount)
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
