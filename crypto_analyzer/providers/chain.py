"""
Provider chains: ordered fallback logic with resilience wrappers.

A chain tries providers in priority order. If the primary fails (after retries),
the next provider is tried. Circuit breakers skip providers known to be down.
Last-known-good caching prevents data gaps during total outages.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import (
    DexSnapshot,
    DexSnapshotProvider,
    ProviderHealth,
    ProviderStatus,
    SpotPriceProvider,
    SpotQuote,
)
from .resilience import CircuitBreaker, LastKnownGoodCache, RetryConfig, resilient_call

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SpotPriceChain:
    """
    Ordered chain of spot price providers with automatic fallback.

    Tries each provider in priority order. Circuit breakers skip providers
    that are known to be failing. Results are cached as last-known-good
    so transient outages don't produce gaps.
    """

    def __init__(
        self,
        providers: List[SpotPriceProvider],
        retry_config: Optional[RetryConfig] = None,
        lkg_max_age_seconds: float = 300.0,
    ) -> None:
        self._providers = providers
        self._retry_config = retry_config or RetryConfig()
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._health: Dict[str, ProviderHealth] = {}
        self._lkg = LastKnownGoodCache(max_age_seconds=lkg_max_age_seconds)

        for p in providers:
            name = p.provider_name
            self._breakers[name] = CircuitBreaker(provider_name=name)
            self._health[name] = ProviderHealth(provider_name=name)

    def get_spot(self, symbol: str) -> SpotQuote:
        """
        Fetch spot price using the provider chain.

        Tries each provider in order, with circuit breaker + retry protection.
        Falls back to last-known-good if all providers fail.
        """
        errors: List[str] = []
        for provider in self._providers:
            name = provider.provider_name
            breaker = self._breakers[name]
            health = self._health[name]

            if breaker.is_open:
                errors.append(f"{name}: circuit breaker OPEN")
                continue

            try:
                quote = resilient_call(
                    provider.get_spot,
                    symbol,
                    retry_config=self._retry_config,
                    circuit_breaker=breaker,
                )
                if quote.is_valid():
                    health.record_success()
                    self._lkg.put(f"spot:{symbol}", quote)
                    return quote
                else:
                    msg = f"{name}: invalid quote (price={quote.price_usd})"
                    errors.append(msg)
                    health.record_failure(msg)
            except Exception as exc:
                msg = f"{name}: {type(exc).__name__}: {exc}"
                errors.append(msg)
                health.record_failure(str(exc))

        cached = self._lkg.get(f"spot:{symbol}")
        if cached is not None:
            logger.warning(
                "All spot providers failed for %s, using last-known-good from %s",
                symbol, cached.provider_name,
            )
            return SpotQuote(
                symbol=cached.symbol,
                price_usd=cached.price_usd,
                provider_name=f"{cached.provider_name}(lkg)",
                fetched_at_utc=cached.fetched_at_utc,
                status=ProviderStatus.DEGRADED,
            )

        raise RuntimeError(
            f"All spot providers failed for {symbol}: {'; '.join(errors)}"
        )

    def get_health(self) -> Dict[str, ProviderHealth]:
        """Return health status for all providers in the chain."""
        return dict(self._health)

    def get_breaker_states(self) -> Dict[str, str]:
        """Return circuit breaker state for each provider."""
        return {name: cb.state for name, cb in self._breakers.items()}


class DexSnapshotChain:
    """
    Ordered chain of DEX snapshot providers with automatic fallback.
    """

    def __init__(
        self,
        providers: List[DexSnapshotProvider],
        retry_config: Optional[RetryConfig] = None,
        lkg_max_age_seconds: float = 300.0,
    ) -> None:
        self._providers = providers
        self._retry_config = retry_config or RetryConfig()
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._health: Dict[str, ProviderHealth] = {}
        self._lkg = LastKnownGoodCache(max_age_seconds=lkg_max_age_seconds)

        for p in providers:
            name = p.provider_name
            self._breakers[name] = CircuitBreaker(provider_name=name)
            self._health[name] = ProviderHealth(provider_name=name)

    def get_snapshot(self, chain_id: str, pair_address: str) -> DexSnapshot:
        """
        Fetch DEX snapshot using the provider chain.
        """
        errors: List[str] = []
        cache_key = f"dex:{chain_id}:{pair_address}"

        for provider in self._providers:
            name = provider.provider_name
            breaker = self._breakers[name]
            health = self._health[name]

            if breaker.is_open:
                errors.append(f"{name}: circuit breaker OPEN")
                continue

            try:
                snapshot = resilient_call(
                    provider.get_snapshot,
                    chain_id,
                    pair_address,
                    retry_config=self._retry_config,
                    circuit_breaker=breaker,
                )
                if snapshot.is_valid():
                    health.record_success()
                    self._lkg.put(cache_key, snapshot)
                    return snapshot
                else:
                    msg = f"{name}: invalid snapshot (price={snapshot.dex_price_usd})"
                    errors.append(msg)
                    health.record_failure(msg)
            except Exception as exc:
                msg = f"{name}: {type(exc).__name__}: {exc}"
                errors.append(msg)
                health.record_failure(str(exc))

        cached = self._lkg.get(cache_key)
        if cached is not None:
            logger.warning(
                "All DEX providers failed for %s:%s, using last-known-good",
                chain_id, pair_address,
            )
            return DexSnapshot(
                chain_id=cached.chain_id,
                pair_address=cached.pair_address,
                dex_id=cached.dex_id,
                base_symbol=cached.base_symbol,
                quote_symbol=cached.quote_symbol,
                dex_price_usd=cached.dex_price_usd,
                dex_price_native=cached.dex_price_native,
                liquidity_usd=cached.liquidity_usd,
                vol_h24=cached.vol_h24,
                txns_h24_buys=cached.txns_h24_buys,
                txns_h24_sells=cached.txns_h24_sells,
                provider_name=f"{cached.provider_name}(lkg)",
                fetched_at_utc=cached.fetched_at_utc,
                status=ProviderStatus.DEGRADED,
                raw_json=cached.raw_json,
            )

        raise RuntimeError(
            f"All DEX providers failed for {chain_id}:{pair_address}: "
            f"{'; '.join(errors)}"
        )

    def search_pairs(
        self, query: str, chain_id: str = "solana"
    ) -> list[Dict[str, Any]]:
        """Search pairs using the first available provider."""
        for provider in self._providers:
            name = provider.provider_name
            breaker = self._breakers.get(name)
            if breaker and breaker.is_open:
                continue
            try:
                return provider.search_pairs(query, chain_id)
            except Exception as exc:
                logger.debug("Search failed on %s: %s", name, exc)
        return []

    def get_health(self) -> Dict[str, ProviderHealth]:
        return dict(self._health)

    def get_breaker_states(self) -> Dict[str, str]:
        return {name: cb.state for name, cb in self._breakers.items()}
