"""
Tests for fake providers: deterministic data, fail-N-then-succeed, always-fail behavior.

No live network; validates that fakes behave as required for ingest cycle tests.
"""

from __future__ import annotations

import pytest

from crypto_analyzer.providers.chain import DexSnapshotChain, SpotPriceChain
from crypto_analyzer.providers.resilience import RetryConfig

from .providers import (
    FAKE_FETCHED_AT,
    FakeDexProvider,
    FakeDexProviderAlwaysFail,
    FakeDexProviderFailNThenSucceed,
    FakeSpotProvider,
    FakeSpotProviderAlwaysFail,
    FakeSpotProviderFailNThenSucceed,
)


class TestFakeSpotProvider:
    """Always-succeed fake returns deterministic data."""

    def test_deterministic_quotes(self):
        p = FakeSpotProvider("ok", {"SOL": 200.0, "BTC": 60_000.0})
        q1 = p.get_spot("SOL")
        q2 = p.get_spot("SOL")
        assert q1.symbol == "SOL"
        assert q1.price_usd == 200.0
        assert q1.provider_name == "ok"
        assert q1.fetched_at_utc == FAKE_FETCHED_AT
        assert q2.price_usd == q1.price_usd

    def test_chain_uses_primary(self):
        primary = FakeSpotProvider("primary", {"SOL": 150.0})
        chain = SpotPriceChain([primary], retry_config=RetryConfig(max_retries=1))
        q = chain.get_spot("SOL")
        assert q.provider_name == "primary"
        assert q.price_usd == 150.0


class TestFakeSpotProviderFailNThenSucceed:
    """Fail N times then succeed."""

    def test_fails_then_succeeds(self):
        p = FakeSpotProviderFailNThenSucceed("flaky", fail_times=2, prices={"SOL": 155.0})
        with pytest.raises(RuntimeError, match="simulated failure"):
            p.get_spot("SOL")
        with pytest.raises(RuntimeError, match="simulated failure"):
            p.get_spot("SOL")
        q = p.get_spot("SOL")
        assert q.price_usd == 155.0
        assert q.provider_name == "flaky"

    def test_chain_fallback_after_n_failures(self):
        flaky = FakeSpotProviderFailNThenSucceed("flaky", fail_times=2, prices={"SOL": 155.0})
        backup = FakeSpotProvider("backup", {"SOL": 160.0})
        chain = SpotPriceChain(
            [flaky, backup],
            retry_config=RetryConfig(max_retries=1),
        )
        # First call: flaky fails, backup used (retry config may call flaky 1 or 2 times)
        q1 = chain.get_spot("SOL")
        assert q1.provider_name == "backup"
        assert q1.price_usd == 160.0
        # Circuit breaker opens after repeated failures, so second call still uses backup
        q2 = chain.get_spot("SOL")
        assert q2.provider_name == "backup"
        assert q2.price_usd == 160.0


class TestFakeSpotProviderAlwaysFail:
    """Always-fail fake."""

    def test_always_raises(self):
        p = FakeSpotProviderAlwaysFail("bad")
        for _ in range(3):
            with pytest.raises(RuntimeError, match="always fails"):
                p.get_spot("SOL")

    def test_chain_raises_when_all_fail(self):
        a = FakeSpotProviderAlwaysFail("a")
        b = FakeSpotProviderAlwaysFail("b")
        chain = SpotPriceChain([a, b], retry_config=RetryConfig(max_retries=1))
        with pytest.raises(RuntimeError, match="All spot providers failed"):
            chain.get_spot("SOL")


class TestFakeDexProvider:
    """Always-succeed DEX fake."""

    def test_deterministic_snapshot(self):
        p = FakeDexProvider("dex_ok", dex_price_usd=200.0, liquidity_usd=2_000_000.0)
        s = p.get_snapshot("solana", "addr1")
        assert s.chain_id == "solana"
        assert s.pair_address == "addr1"
        assert s.dex_price_usd == 200.0
        assert s.liquidity_usd == 2_000_000.0
        assert s.provider_name == "dex_ok"


class TestFakeDexProviderFailNThenSucceed:
    """DEX fail N then succeed."""

    def test_fails_then_succeeds(self):
        p = FakeDexProviderFailNThenSucceed("dex_flaky", fail_times=1, dex_price_usd=170.0)
        with pytest.raises(RuntimeError, match="simulated failure"):
            p.get_snapshot("solana", "addr")
        s = p.get_snapshot("solana", "addr")
        assert s.dex_price_usd == 170.0


class TestFakeDexProviderAlwaysFail:
    """DEX always fail."""

    def test_chain_raises_when_all_fail(self):
        chain = DexSnapshotChain(
            [FakeDexProviderAlwaysFail("a"), FakeDexProviderAlwaysFail("b")],
            retry_config=RetryConfig(max_retries=1),
        )
        with pytest.raises(RuntimeError, match="All DEX providers failed"):
            chain.get_snapshot("solana", "addr")
