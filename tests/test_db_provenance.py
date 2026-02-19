"""
Tests for database provenance tracking and provider health persistence.

Verifies that:
- Spot price records include provider_name and fetch_status
- DEX snapshot records include provider provenance
- Provider health is persisted and loadable
- Migrations are idempotent
"""
from __future__ import annotations

import sqlite3

import pytest

from crypto_analyzer.db.health import ProviderHealthStore
from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.db.writer import DbWriter
from crypto_analyzer.providers.base import (
    DexSnapshot,
    ProviderHealth,
    ProviderStatus,
    SpotQuote,
)


@pytest.fixture
def db_conn():
    """Create an in-memory SQLite database with migrations applied."""
    conn = sqlite3.connect(":memory:")
    run_migrations(conn)
    yield conn
    conn.close()


class TestDbWriter:
    def test_write_spot_price_with_provenance(self, db_conn):
        writer = DbWriter(db_conn)
        quote = SpotQuote(
            symbol="BTC",
            price_usd=50000.0,
            provider_name="coinbase",
            fetched_at_utc="2026-01-01T00:00:00+00:00",
        )

        result = writer.write_spot_price("2026-01-01T00:00:00+00:00", quote)
        writer.commit()
        assert result is True

        cur = db_conn.execute(
            "SELECT symbol, spot_price_usd, provider_name, fetch_status "
            "FROM spot_price_snapshots"
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "BTC"
        assert row[1] == 50000.0
        assert row[2] == "coinbase"
        assert row[3] == "OK"

    def test_write_spot_price_degraded(self, db_conn):
        writer = DbWriter(db_conn)
        quote = SpotQuote(
            symbol="ETH",
            price_usd=3000.0,
            provider_name="kraken(lkg)",
            fetched_at_utc="2026-01-01T00:00:00+00:00",
            status=ProviderStatus.DEGRADED,
        )

        result = writer.write_spot_price("2026-01-01T00:00:00+00:00", quote)
        writer.commit()
        assert result is True

        cur = db_conn.execute(
            "SELECT fetch_status FROM spot_price_snapshots WHERE symbol = 'ETH'"
        )
        row = cur.fetchone()
        assert row[0] == "DEGRADED"

    def test_reject_down_spot_price(self, db_conn):
        writer = DbWriter(db_conn)
        quote = SpotQuote(
            symbol="SOL",
            price_usd=0.0,
            provider_name="broken",
            fetched_at_utc="2026-01-01T00:00:00+00:00",
            status=ProviderStatus.DOWN,
            error_message="provider crashed",
        )

        result = writer.write_spot_price("2026-01-01T00:00:00+00:00", quote)
        assert result is False

    def test_write_dex_snapshot_with_provenance(self, db_conn):
        writer = DbWriter(db_conn)
        snapshot = DexSnapshot(
            chain_id="solana",
            pair_address="abc123",
            dex_id="orca",
            base_symbol="SOL",
            quote_symbol="USDC",
            dex_price_usd=150.0,
            dex_price_native=1.0,
            liquidity_usd=1_000_000.0,
            vol_h24=500_000.0,
            txns_h24_buys=100,
            txns_h24_sells=80,
            provider_name="dexscreener",
            fetched_at_utc="2026-01-01T00:00:00+00:00",
        )

        result = writer.write_dex_snapshot(
            "2026-01-01T00:00:00+00:00", snapshot, 150.0, "coinbase"
        )
        writer.commit()
        assert result is True

        cur = db_conn.execute(
            "SELECT chain_id, pair_address, provider_name, fetch_status "
            "FROM sol_monitor_snapshots"
        )
        row = cur.fetchone()
        assert row[0] == "solana"
        assert row[1] == "abc123"
        assert row[2] == "dexscreener"
        assert row[3] == "OK"

    def test_batch_spot_writes(self, db_conn):
        writer = DbWriter(db_conn)
        quotes = [
            SpotQuote("BTC", 50000.0, "coinbase", "2026-01-01T00:00:00+00:00"),
            SpotQuote("ETH", 3000.0, "coinbase", "2026-01-01T00:00:00+00:00"),
            SpotQuote("SOL", 150.0, "kraken", "2026-01-01T00:00:00+00:00"),
        ]

        written = writer.write_spot_prices_batch("2026-01-01T00:00:00+00:00", quotes)
        writer.commit()
        assert written == 3

        cur = db_conn.execute("SELECT COUNT(*) FROM spot_price_snapshots")
        assert cur.fetchone()[0] == 3


class TestProviderHealthStore:
    def test_upsert_and_load(self, db_conn):
        store = ProviderHealthStore(db_conn)
        health = ProviderHealth(
            provider_name="coinbase",
            status=ProviderStatus.OK,
            last_ok_at="2026-01-01T00:00:00+00:00",
            fail_count=0,
        )

        store.upsert(health)
        loaded = store.load_all()
        assert len(loaded) == 1
        assert loaded[0].provider_name == "coinbase"
        assert loaded[0].status == ProviderStatus.OK

    def test_upsert_updates_existing(self, db_conn):
        store = ProviderHealthStore(db_conn)
        h1 = ProviderHealth("test", ProviderStatus.OK, fail_count=0)
        store.upsert(h1)

        h2 = ProviderHealth("test", ProviderStatus.DEGRADED, fail_count=3, last_error="timeout")
        store.upsert(h2)

        loaded = store.load_as_dict()
        assert loaded["test"].status == ProviderStatus.DEGRADED
        assert loaded["test"].fail_count == 3
        assert loaded["test"].last_error == "timeout"

    def test_load_empty(self, db_conn):
        store = ProviderHealthStore(db_conn)
        assert store.load_all() == []

    def test_upsert_all(self, db_conn):
        store = ProviderHealthStore(db_conn)
        healths = {
            "coinbase": ProviderHealth("coinbase", ProviderStatus.OK),
            "kraken": ProviderHealth("kraken", ProviderStatus.DEGRADED, fail_count=2),
        }
        store.upsert_all(healths)

        loaded = store.load_as_dict()
        assert len(loaded) == 2
        assert loaded["coinbase"].status == ProviderStatus.OK
        assert loaded["kraken"].status == ProviderStatus.DEGRADED


class TestMigrations:
    def test_idempotent_migrations(self, db_conn):
        """Running migrations twice should not raise."""
        run_migrations(db_conn)
        run_migrations(db_conn)

        cur = db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cur.fetchall()}
        assert "sol_monitor_snapshots" in tables
        assert "spot_price_snapshots" in tables
        assert "provider_health" in tables
        assert "universe_allowlist" in tables

    def test_provenance_columns_exist(self, db_conn):
        cur = db_conn.execute("PRAGMA table_info(spot_price_snapshots)")
        columns = {row[1] for row in cur.fetchall()}
        assert "provider_name" in columns
        assert "fetched_at_utc" in columns
        assert "fetch_status" in columns
        assert "error_message" in columns

    def test_dex_provenance_columns_exist(self, db_conn):
        cur = db_conn.execute("PRAGMA table_info(sol_monitor_snapshots)")
        columns = {row[1] for row in cur.fetchall()}
        assert "provider_name" in columns
        assert "fetched_at_utc" in columns
        assert "fetch_status" in columns
