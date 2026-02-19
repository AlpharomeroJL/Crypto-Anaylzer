"""CEX (centralized exchange) spot price providers."""
from __future__ import annotations

from .coinbase import CoinbaseSpotProvider
from .kraken import KrakenSpotProvider

__all__ = ["CoinbaseSpotProvider", "KrakenSpotProvider"]
