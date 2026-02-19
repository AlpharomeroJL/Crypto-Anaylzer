"""
Integration smoke test: one poll cycle with mocked HTTP to a temp SQLite DB.

Verifies the full path from provider -> chain -> db_writer -> SQLite without
any live network calls.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from crypto_analyzer.db.health import ProviderHealthStore
from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.db.writer import DbWriter
from crypto_analyzer.providers.base import DexSnapshot, ProviderStatus, SpotQuote
from crypto_analyzer.providers.cex.coinbase import CoinbaseSpotProvider
from crypto_analyzer.providers.cex.kraken import KrakenSpotProvider
from crypto_analyzer.providers.chain import DexSnapshotChain, SpotPriceChain
from crypto_analyzer.providers.dex.dexscreener import DexscreenerDexProvider
from crypto_analyzer.providers.registry import ProviderRegistry
from crypto_analyzer.providers.resilience import RetryConfig


@pytest.fixture
def temp_db():
    conn = sqlite3.connect(":memory:")
    run_migrations(conn)
    yield conn
    conn.close()


class TestRegistryIntegration:
    def test_register_and_build_chain(self):
        registry = ProviderRegistry()
        registry.register_spot("coinbase", CoinbaseSpotProvider)
        registry.register_spot("kraken", KrakenSpotProvider)
        registry.register_dex("dexscreener", DexscreenerDexProvider)

        assert "coinbase" in registry.spot_names
        assert "kraken" in registry.spot_names
        assert "dexscreener" in registry.dex_names

        spot_chain = registry.build_spot_chain(["coinbase", "kraken"])
        assert len(spot_chain) == 2
        assert spot_chain[0].provider_name == "coinbase"
        assert spot_chain[1].provider_name == "kraken"


class TestMockedPollCycle:
    """Simulate one full poll cycle with mocked HTTP responses."""

    @patch("crypto_analyzer.providers.cex.coinbase.requests.get")
    def test_coinbase_provider_mocked(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"amount": "50000.00"}}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = CoinbaseSpotProvider()
        quote = provider.get_spot("BTC")
        assert quote.symbol == "BTC"
        assert quote.price_usd == 50000.0
        assert quote.provider_name == "coinbase"

    @patch("crypto_analyzer.providers.cex.kraken.requests.get")
    def test_kraken_provider_mocked(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "error": [],
            "result": {"XXBTZUSD": {"c": ["49999.50", "0.1"]}},
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = KrakenSpotProvider()
        quote = provider.get_spot("BTC")
        assert quote.symbol == "BTC"
        assert quote.price_usd == 49999.50
        assert quote.provider_name == "kraken"

    @patch("crypto_analyzer.providers.dex.dexscreener.requests.get")
    def test_dexscreener_provider_mocked(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "pair": {
                "chainId": "solana",
                "pairAddress": "abc123",
                "dexId": "orca",
                "priceUsd": "150.25",
                "priceNative": "1.0",
                "baseToken": {"symbol": "SOL"},
                "quoteToken": {"symbol": "USDC"},
                "liquidity": {"usd": 1000000},
                "volume": {"h24": 500000},
                "txns": {"h24": {"buys": 100, "sells": 80}},
            }
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = DexscreenerDexProvider()
        snap = provider.get_snapshot("solana", "abc123")
        assert snap.chain_id == "solana"
        assert snap.dex_price_usd == 150.25
        assert snap.base_symbol == "SOL"
        assert snap.provider_name == "dexscreener"

    def test_full_poll_cycle_to_sqlite(self, temp_db):
        """Simulate one complete poll cycle writing to a temp SQLite DB."""

        # Create mock providers instead of patching HTTP
        class FakeCoinbase:
            provider_name = "coinbase"

            def get_spot(self, symbol):
                prices = {"SOL": 150.0, "ETH": 3000.0, "BTC": 50000.0}
                return SpotQuote(
                    symbol=symbol,
                    price_usd=prices.get(symbol, 100.0),
                    provider_name="coinbase",
                    fetched_at_utc="2026-01-01T00:00:00+00:00",
                )

        class FakeDex:
            provider_name = "dexscreener"

            def get_snapshot(self, chain_id, pair_address):
                return DexSnapshot(
                    chain_id=chain_id,
                    pair_address=pair_address,
                    dex_id="orca",
                    base_symbol="SOL",
                    quote_symbol="USDC",
                    dex_price_usd=150.0,
                    dex_price_native=1.0,
                    liquidity_usd=1000000.0,
                    vol_h24=500000.0,
                    txns_h24_buys=100,
                    txns_h24_sells=80,
                    provider_name="dexscreener",
                    fetched_at_utc="2026-01-01T00:00:00+00:00",
                )

            def search_pairs(self, query, chain_id="solana"):
                return []

        # Build chains with fake providers
        spot_chain = SpotPriceChain(
            [FakeCoinbase()],
            retry_config=RetryConfig(max_retries=1),
        )
        dex_chain = DexSnapshotChain(
            [FakeDex()],
            retry_config=RetryConfig(max_retries=1),
        )

        writer = DbWriter(temp_db)
        health_store = ProviderHealthStore(temp_db)
        ts = "2026-01-01T00:00:00+00:00"

        # Poll spot prices
        for symbol in ["SOL", "ETH", "BTC"]:
            quote = spot_chain.get_spot(symbol)
            writer.write_spot_price(ts, quote)

        # Poll one DEX pair
        snap = dex_chain.get_snapshot("solana", "test_pair")
        writer.write_dex_snapshot(ts, snap, 150.0, "coinbase")
        writer.commit()

        # Persist health
        health_store.upsert_all(spot_chain.get_health())
        health_store.upsert_all(dex_chain.get_health())

        # Verify spot prices written
        cur = temp_db.execute("SELECT COUNT(*) FROM spot_price_snapshots")
        assert cur.fetchone()[0] == 3

        # Verify DEX snapshot written
        cur = temp_db.execute("SELECT COUNT(*) FROM sol_monitor_snapshots")
        assert cur.fetchone()[0] == 1

        # Verify provenance
        cur = temp_db.execute("SELECT provider_name, fetch_status FROM spot_price_snapshots WHERE symbol = 'BTC'")
        row = cur.fetchone()
        assert row[0] == "coinbase"
        assert row[1] == "OK"

        # Verify health persisted
        health_data = health_store.load_as_dict()
        assert "coinbase" in health_data
        assert health_data["coinbase"].status == ProviderStatus.OK

    def test_fallback_provenance_tracked(self, temp_db):
        """When primary fails and fallback succeeds, provenance shows fallback provider."""

        class FailingProvider:
            provider_name = "coinbase"

            def get_spot(self, symbol):
                raise RuntimeError("Coinbase is down")

        class WorkingProvider:
            provider_name = "kraken"

            def get_spot(self, symbol):
                return SpotQuote(
                    symbol=symbol,
                    price_usd=149.50,
                    provider_name="kraken",
                    fetched_at_utc="2026-01-01T00:00:00+00:00",
                )

        chain = SpotPriceChain(
            [FailingProvider(), WorkingProvider()],
            retry_config=RetryConfig(max_retries=1, base_delay_s=0.01),
        )

        writer = DbWriter(temp_db)
        quote = chain.get_spot("SOL")
        writer.write_spot_price("2026-01-01T00:00:00+00:00", quote)
        writer.commit()

        cur = temp_db.execute("SELECT provider_name, fetch_status FROM spot_price_snapshots")
        row = cur.fetchone()
        assert row[0] == "kraken"
        assert row[1] == "OK"
