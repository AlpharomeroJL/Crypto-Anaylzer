"""
Tests for the provider chain fallback logic.

Verifies that:
- Primary provider is used when healthy
- Fallback providers are tried when primary fails
- Circuit breakers prevent repeated calls to failing providers
- Last-known-good caching fills gaps during total outages
- Data quality gates reject invalid quotes
"""
from __future__ import annotations

import time

import pytest

from crypto_analyzer.providers.base import (
    DexSnapshot,
    ProviderStatus,
    SpotQuote,
)
from crypto_analyzer.providers.chain import DexSnapshotChain, SpotPriceChain
from crypto_analyzer.providers.resilience import CircuitBreaker, RetryConfig

# ---------------------------------------------------------------------------
# Helpers: mock providers
# ---------------------------------------------------------------------------

class MockSpotProvider:
    def __init__(self, name: str, prices: dict | None = None, fail: bool = False):
        self._name = name
        self._prices = prices or {}
        self._fail = fail
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return self._name

    def get_spot(self, symbol: str) -> SpotQuote:
        self.call_count += 1
        if self._fail:
            raise RuntimeError(f"{self._name} is down")
        price = self._prices.get(symbol, 100.0)
        return SpotQuote(
            symbol=symbol,
            price_usd=price,
            provider_name=self._name,
            fetched_at_utc="2026-01-01T00:00:00+00:00",
        )


class MockDexProvider:
    def __init__(self, name: str, fail: bool = False):
        self._name = name
        self._fail = fail
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return self._name

    def get_snapshot(self, chain_id: str, pair_address: str) -> DexSnapshot:
        self.call_count += 1
        if self._fail:
            raise RuntimeError(f"{self._name} is down")
        return DexSnapshot(
            chain_id=chain_id,
            pair_address=pair_address,
            dex_id="test_dex",
            base_symbol="SOL",
            quote_symbol="USDC",
            dex_price_usd=150.0,
            dex_price_native=1.0,
            liquidity_usd=1_000_000.0,
            vol_h24=500_000.0,
            txns_h24_buys=100,
            txns_h24_sells=80,
            provider_name=self._name,
            fetched_at_utc="2026-01-01T00:00:00+00:00",
        )

    def search_pairs(self, query: str, chain_id: str = "solana") -> list:
        return []


# ---------------------------------------------------------------------------
# Spot chain tests
# ---------------------------------------------------------------------------

class TestSpotPriceChain:
    def test_primary_provider_used_when_healthy(self):
        primary = MockSpotProvider("coinbase", {"BTC": 50000.0})
        fallback = MockSpotProvider("kraken", {"BTC": 50001.0})
        chain = SpotPriceChain(
            [primary, fallback],
            retry_config=RetryConfig(max_retries=1),
        )

        quote = chain.get_spot("BTC")
        assert quote.provider_name == "coinbase"
        assert quote.price_usd == 50000.0
        assert primary.call_count == 1
        assert fallback.call_count == 0

    def test_fallback_used_when_primary_fails(self):
        primary = MockSpotProvider("coinbase", fail=True)
        fallback = MockSpotProvider("kraken", {"BTC": 50001.0})
        chain = SpotPriceChain(
            [primary, fallback],
            retry_config=RetryConfig(max_retries=1),
        )

        quote = chain.get_spot("BTC")
        assert quote.provider_name == "kraken"
        assert quote.price_usd == 50001.0

    def test_all_fail_raises_runtime_error(self):
        p1 = MockSpotProvider("p1", fail=True)
        p2 = MockSpotProvider("p2", fail=True)
        chain = SpotPriceChain(
            [p1, p2],
            retry_config=RetryConfig(max_retries=1),
        )

        with pytest.raises(RuntimeError, match="All spot providers failed"):
            chain.get_spot("BTC")

    def test_last_known_good_on_total_failure(self):
        primary = MockSpotProvider("coinbase", {"BTC": 50000.0})
        chain = SpotPriceChain(
            [primary],
            retry_config=RetryConfig(max_retries=1),
        )

        quote1 = chain.get_spot("BTC")
        assert quote1.price_usd == 50000.0

        primary._fail = True
        quote2 = chain.get_spot("BTC")
        assert quote2.price_usd == 50000.0
        assert "lkg" in quote2.provider_name
        assert quote2.status == ProviderStatus.DEGRADED

    def test_health_tracking(self):
        primary = MockSpotProvider("coinbase", fail=True)
        fallback = MockSpotProvider("kraken", {"BTC": 50001.0})
        chain = SpotPriceChain(
            [primary, fallback],
            retry_config=RetryConfig(max_retries=1),
        )

        chain.get_spot("BTC")
        health = chain.get_health()
        assert health["coinbase"].fail_count > 0
        assert health["kraken"].status == ProviderStatus.OK

    def test_data_quality_gate_rejects_zero_price(self):
        provider = MockSpotProvider("bad", {"BTC": 0.0})
        fallback = MockSpotProvider("good", {"BTC": 50000.0})
        chain = SpotPriceChain(
            [provider, fallback],
            retry_config=RetryConfig(max_retries=1),
        )

        quote = chain.get_spot("BTC")
        assert quote.provider_name == "good"
        assert quote.price_usd == 50000.0


# ---------------------------------------------------------------------------
# DEX chain tests
# ---------------------------------------------------------------------------

class TestDexSnapshotChain:
    def test_primary_dex_provider_used(self):
        primary = MockDexProvider("dexscreener")
        chain = DexSnapshotChain(
            [primary],
            retry_config=RetryConfig(max_retries=1),
        )

        snap = chain.get_snapshot("solana", "abc123")
        assert snap.provider_name == "dexscreener"
        assert snap.dex_price_usd == 150.0

    def test_dex_fallback(self):
        primary = MockDexProvider("dex_a", fail=True)
        fallback = MockDexProvider("dex_b")
        chain = DexSnapshotChain(
            [primary, fallback],
            retry_config=RetryConfig(max_retries=1),
        )

        snap = chain.get_snapshot("solana", "abc123")
        assert snap.provider_name == "dex_b"

    def test_dex_lkg_cache(self):
        provider = MockDexProvider("dexscreener")
        chain = DexSnapshotChain(
            [provider],
            retry_config=RetryConfig(max_retries=1),
        )

        snap1 = chain.get_snapshot("solana", "abc123")
        assert snap1.is_valid()

        provider._fail = True
        snap2 = chain.get_snapshot("solana", "abc123")
        assert "lkg" in snap2.provider_name
        assert snap2.status == ProviderStatus.DEGRADED


# ---------------------------------------------------------------------------
# Circuit breaker tests
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(provider_name="test", failure_threshold=3)
        assert cb.state == "CLOSED"
        assert not cb.is_open

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(provider_name="test", failure_threshold=3)
        cb.record_failure("error 1")
        assert cb.state == "CLOSED"
        cb.record_failure("error 2")
        assert cb.state == "CLOSED"
        cb.record_failure("error 3")
        assert cb.state == "OPEN"
        assert cb.is_open

    def test_half_open_after_cooldown(self):
        cb = CircuitBreaker(
            provider_name="test", failure_threshold=1, cooldown_seconds=0.1
        )
        cb.record_failure("error")
        assert cb.state == "OPEN"

        time.sleep(0.15)
        assert cb.state == "HALF_OPEN"

    def test_closes_on_success(self):
        cb = CircuitBreaker(provider_name="test", failure_threshold=1)
        cb.record_failure("error")
        assert cb.is_open

        cb._state = "HALF_OPEN"
        cb.record_success()
        assert cb.state == "CLOSED"
        assert not cb.is_open

    def test_circuit_breaker_skips_open_providers(self):
        primary = MockSpotProvider("coinbase", fail=True)
        fallback = MockSpotProvider("kraken", {"BTC": 50001.0})
        chain = SpotPriceChain(
            [primary, fallback],
            retry_config=RetryConfig(max_retries=1),
        )

        for _ in range(5):
            chain.get_spot("BTC")

        breakers = chain.get_breaker_states()
        assert breakers.get("coinbase") == "OPEN"

        primary.call_count = 0
        chain.get_spot("BTC")
        assert primary.call_count == 0

    def test_reset(self):
        cb = CircuitBreaker(provider_name="test", failure_threshold=1)
        cb.record_failure("err")
        assert cb.is_open
        cb.reset()
        assert cb.state == "CLOSED"
        assert not cb.is_open


# ---------------------------------------------------------------------------
# Retry behavior tests
# ---------------------------------------------------------------------------

class TestRetryBehavior:
    def test_retries_on_transient_failure(self):
        call_count = 0

        def flaky_fetch(symbol: str) -> SpotQuote:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient error")
            return SpotQuote(
                symbol=symbol,
                price_usd=50000.0,
                provider_name="test",
                fetched_at_utc="2026-01-01T00:00:00+00:00",
            )

        from crypto_analyzer.providers.resilience import resilient_call

        result = resilient_call(
            flaky_fetch,
            "BTC",
            retry_config=RetryConfig(max_retries=3, base_delay_s=0.01),
        )
        assert result.price_usd == 50000.0
        assert call_count == 3

    def test_exhausts_retries_and_raises(self):
        def always_fail(symbol: str) -> SpotQuote:
            raise RuntimeError("permanent failure")

        from crypto_analyzer.providers.resilience import resilient_call

        with pytest.raises(RuntimeError, match="permanent failure"):
            resilient_call(
                always_fail,
                "BTC",
                retry_config=RetryConfig(max_retries=2, base_delay_s=0.01),
            )
