"""
Provider interfaces and data contracts.

All providers implement one of two protocols:
- SpotPriceProvider: CEX spot price feeds (Coinbase, Kraken, etc.)
- DexSnapshotProvider: DEX pair snapshots (Dexscreener, etc.)

Data is returned via frozen dataclasses for immutability and type safety.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Protocol, runtime_checkable


class ProviderStatus(enum.Enum):
    """Health status of a data provider."""

    OK = "OK"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"


@dataclass(frozen=True)
class SpotQuote:
    """Immutable spot price quote from a CEX provider."""

    symbol: str
    price_usd: float
    provider_name: str
    fetched_at_utc: str
    status: ProviderStatus = ProviderStatus.OK
    error_message: Optional[str] = None

    def is_valid(self) -> bool:
        return self.price_usd is not None and self.price_usd > 0 and self.status == ProviderStatus.OK


@dataclass(frozen=True)
class DexSnapshot:
    """Immutable DEX pair snapshot from a DEX provider."""

    chain_id: str
    pair_address: str
    dex_id: Optional[str]
    base_symbol: Optional[str]
    quote_symbol: Optional[str]
    dex_price_usd: Optional[float]
    dex_price_native: Optional[float]
    liquidity_usd: Optional[float]
    vol_h24: Optional[float]
    txns_h24_buys: Optional[int]
    txns_h24_sells: Optional[int]
    provider_name: str
    fetched_at_utc: str
    status: ProviderStatus = ProviderStatus.OK
    error_message: Optional[str] = None
    raw_json: Optional[str] = None

    def is_valid(self) -> bool:
        return self.dex_price_usd is not None and self.dex_price_usd > 0 and self.status == ProviderStatus.OK


@dataclass
class ProviderHealth:
    """Mutable health state for a single provider instance."""

    provider_name: str
    status: ProviderStatus = ProviderStatus.OK
    last_ok_at: Optional[str] = None
    fail_count: int = 0
    last_error: Optional[str] = None
    disabled_until: Optional[str] = None

    def record_success(self) -> None:
        self.status = ProviderStatus.OK
        self.fail_count = 0
        self.last_ok_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.last_error = None
        self.disabled_until = None

    def record_failure(self, error: str) -> None:
        self.fail_count += 1
        self.last_error = error[:500]
        if self.fail_count >= 5:
            self.status = ProviderStatus.DOWN
        elif self.fail_count >= 2:
            self.status = ProviderStatus.DEGRADED


@runtime_checkable
class SpotPriceProvider(Protocol):
    """Protocol for CEX spot price providers."""

    @property
    def provider_name(self) -> str: ...

    def get_spot(self, symbol: str) -> SpotQuote:
        """Fetch current spot price for a symbol (e.g., 'BTC', 'ETH', 'SOL')."""
        ...


@runtime_checkable
class DexSnapshotProvider(Protocol):
    """Protocol for DEX snapshot providers."""

    @property
    def provider_name(self) -> str: ...

    def get_snapshot(self, chain_id: str, pair_address: str) -> DexSnapshot:
        """Fetch current snapshot for a DEX pair."""
        ...

    def search_pairs(self, query: str, chain_id: str = "solana") -> list[Dict[str, Any]]:
        """Search for pairs matching a query string. Returns raw pair dicts."""
        ...
