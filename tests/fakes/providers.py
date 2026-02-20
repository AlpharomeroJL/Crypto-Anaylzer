"""
Fake spot and DEX providers for tests: deterministic data, fail-N-then-succeed, always-fail.

No live network; used by test_ingest_cycle and test_providers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from crypto_analyzer.providers.base import DexSnapshot, SpotQuote

# Deterministic timestamp for reproducible tests.
FAKE_FETCHED_AT = "2026-01-01T00:00:00+00:00"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Spot: always succeed with deterministic data
# ---------------------------------------------------------------------------


class FakeSpotProvider:
    """Spot provider that always returns deterministic quotes. No network."""

    def __init__(
        self,
        name: str,
        prices: Dict[str, float] | None = None,
        *,
        missing_symbols: List[str] | None = None,
    ):
        self._name = name
        self._prices = prices or {"SOL": 150.0, "ETH": 3000.0, "BTC": 50000.0}
        self._missing_symbols = set(missing_symbols or ())
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return self._name

    def get_spot(self, symbol: str) -> SpotQuote:
        self.call_count += 1
        if symbol in self._missing_symbols:
            raise RuntimeError(f"{self._name} does not provide {symbol}")
        price = self._prices.get(symbol, 100.0)
        return SpotQuote(
            symbol=symbol,
            price_usd=price,
            provider_name=self._name,
            fetched_at_utc=FAKE_FETCHED_AT,
        )


# ---------------------------------------------------------------------------
# Spot: fail N times then succeed
# ---------------------------------------------------------------------------


class FakeSpotProviderFailNThenSucceed:
    """Spot provider that fails the first N calls, then returns deterministic quotes."""

    def __init__(self, name: str, fail_times: int, prices: Dict[str, float] | None = None):
        self._name = name
        self._fail_times = fail_times
        self._prices = prices or {"SOL": 150.0, "ETH": 3000.0, "BTC": 50000.0}
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return self._name

    def get_spot(self, symbol: str) -> SpotQuote:
        self.call_count += 1
        if self.call_count <= self._fail_times:
            raise RuntimeError(f"{self._name} simulated failure #{self.call_count}")
        price = self._prices.get(symbol, 100.0)
        return SpotQuote(
            symbol=symbol,
            price_usd=price,
            provider_name=self._name,
            fetched_at_utc=FAKE_FETCHED_AT,
        )


# ---------------------------------------------------------------------------
# Spot: always fail
# ---------------------------------------------------------------------------


class FakeSpotProviderAlwaysFail:
    """Spot provider that always raises. No network."""

    def __init__(self, name: str = "fake_fail"):
        self._name = name
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return self._name

    def get_spot(self, symbol: str) -> SpotQuote:
        self.call_count += 1
        raise RuntimeError(f"{self._name} always fails")


# ---------------------------------------------------------------------------
# DEX: always succeed with deterministic data
# ---------------------------------------------------------------------------


class FakeDexProvider:
    """DEX provider that always returns a deterministic snapshot. No network."""

    def __init__(
        self,
        name: str,
        dex_price_usd: float = 150.0,
        liquidity_usd: float = 1_000_000.0,
        vol_h24: float = 500_000.0,
    ):
        self._name = name
        self._dex_price_usd = dex_price_usd
        self._liquidity_usd = liquidity_usd
        self._vol_h24 = vol_h24
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return self._name

    def get_snapshot(self, chain_id: str, pair_address: str) -> DexSnapshot:
        self.call_count += 1
        return DexSnapshot(
            chain_id=chain_id,
            pair_address=pair_address,
            dex_id="fake_dex",
            base_symbol="SOL",
            quote_symbol="USDC",
            dex_price_usd=self._dex_price_usd,
            dex_price_native=1.0,
            liquidity_usd=self._liquidity_usd,
            vol_h24=self._vol_h24,
            txns_h24_buys=100,
            txns_h24_sells=80,
            provider_name=self._name,
            fetched_at_utc=FAKE_FETCHED_AT,
        )

    def search_pairs(self, query: str, chain_id: str = "solana") -> List[Dict[str, Any]]:
        return []


# ---------------------------------------------------------------------------
# DEX: fail N times then succeed
# ---------------------------------------------------------------------------


class FakeDexProviderFailNThenSucceed:
    """DEX provider that fails the first N calls, then returns deterministic snapshot."""

    def __init__(self, name: str, fail_times: int, dex_price_usd: float = 150.0):
        self._name = name
        self._fail_times = fail_times
        self._dex_price_usd = dex_price_usd
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return self._name

    def get_snapshot(self, chain_id: str, pair_address: str) -> DexSnapshot:
        self.call_count += 1
        if self.call_count <= self._fail_times:
            raise RuntimeError(f"{self._name} simulated failure #{self.call_count}")
        return DexSnapshot(
            chain_id=chain_id,
            pair_address=pair_address,
            dex_id="fake_dex",
            base_symbol="SOL",
            quote_symbol="USDC",
            dex_price_usd=self._dex_price_usd,
            dex_price_native=1.0,
            liquidity_usd=1_000_000.0,
            vol_h24=500_000.0,
            txns_h24_buys=100,
            txns_h24_sells=80,
            provider_name=self._name,
            fetched_at_utc=FAKE_FETCHED_AT,
        )

    def search_pairs(self, query: str, chain_id: str = "solana") -> List[Dict[str, Any]]:
        return []


# ---------------------------------------------------------------------------
# DEX: always fail
# ---------------------------------------------------------------------------


class FakeDexProviderAlwaysFail:
    """DEX provider that always raises. No network."""

    def __init__(self, name: str = "fake_dex_fail"):
        self._name = name
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return self._name

    def get_snapshot(self, chain_id: str, pair_address: str) -> DexSnapshot:
        self.call_count += 1
        raise RuntimeError(f"{self._name} always fails")

    def search_pairs(self, query: str, chain_id: str = "solana") -> List[Dict[str, Any]]:
        return []
