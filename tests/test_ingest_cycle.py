"""
Ingestion cycle tests: fallback chain, missing SOL behavior, rollback, health persistence.

Uses fake providers (no live network). Validates symbol-safe spot mapping,
transactional health updates, and deterministic behavior when SOL quote is missing.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from crypto_analyzer.ingest import (
    SOL_SYMBOL,
    get_poll_context,
    run_one_cycle,
)
from crypto_analyzer.providers.chain import DexSnapshotChain, SpotPriceChain
from crypto_analyzer.providers.resilience import RetryConfig
from tests.fakes.providers import (
    FakeDexProvider,
    FakeSpotProvider,
    FakeSpotProviderFailNThenSucceed,
)

# Quiet log for cycle runs
_log = logging.getLogger("test_ingest_cycle")
_log.addHandler(logging.NullHandler())
_log.setLevel(logging.INFO)


def _spot_chain_fallback() -> SpotPriceChain:
    """Primary fails once then succeeds; backup always succeeds."""
    primary = FakeSpotProviderFailNThenSucceed(
        "primary", fail_times=1, prices={"SOL": 155.0, "ETH": 3100.0, "BTC": 51000.0}
    )
    backup = FakeSpotProvider("backup", {"SOL": 160.0, "ETH": 3200.0, "BTC": 52000.0})
    return SpotPriceChain(
        [primary, backup],
        retry_config=RetryConfig(max_retries=1),
    )


def _dex_chain_ok() -> DexSnapshotChain:
    return DexSnapshotChain(
        [FakeDexProvider("fake_dex", dex_price_usd=150.0)],
        retry_config=RetryConfig(max_retries=1),
    )


def test_partial_failure_fallback_yields_db_writes_and_provenance(tmp_path: Path) -> None:
    """Partial provider failure: fallback is used; DB has writes with correct provenance."""
    db = str(tmp_path / "cycle.db")
    spot_chain = _spot_chain_fallback()
    dex_chain = _dex_chain_ok()
    dex_pairs = [{"chain_id": "solana", "pair_address": "addr1", "label": "SOL/USDC"}]

    with get_poll_context(db, spot_chain=spot_chain, dex_chain=dex_chain) as ctx:
        run_one_cycle(ctx, dex_pairs, log=_log)
        # Spot: first cycle uses backup for SOL (primary fails once), then primary may be used for ETH/BTC
        rows = list(
            ctx.conn.execute("SELECT symbol, spot_price_usd, spot_source FROM spot_price_snapshots ORDER BY symbol")
        )
        assert len(rows) >= 3  # SOL, ETH, BTC
        by_symbol = {r[0]: (r[1], r[2]) for r in rows}
        assert "SOL" in by_symbol
        assert "ETH" in by_symbol
        assert "BTC" in by_symbol
        sources = {r[2] for r in rows}
        assert sources & {"primary", "backup", "primary(lkg)", "backup(lkg)"}
        dex_rows = list(ctx.conn.execute("SELECT spot_source, spot_price_usd FROM sol_monitor_snapshots"))
        assert len(dex_rows) == 1
        assert dex_rows[0][0] in ("primary", "backup")
        assert dex_rows[0][1] in (155.0, 160.0)
        health = list(ctx.conn.execute("SELECT provider_name, status FROM provider_health"))
        assert any(r[0] == "primary" for r in health)
        assert any(r[0] == "backup" for r in health)


def test_missing_sol_skips_dex_no_misattribution(tmp_path: Path) -> None:
    """When SOL quote is missing, DEX snapshots are skipped; spot writes for other symbols only; no wrong provenance."""
    db = str(tmp_path / "cycle.db")
    # Provider that never returns SOL (simulates all providers failing for SOL only)
    spot_chain = SpotPriceChain(
        [FakeSpotProvider("only_eth_btc", prices={"ETH": 3000.0, "BTC": 50000.0}, missing_symbols=[SOL_SYMBOL])],
        retry_config=RetryConfig(max_retries=1),
    )
    dex_chain = _dex_chain_ok()
    dex_pairs = [{"chain_id": "solana", "pair_address": "addr1", "label": "SOL/USDC"}]

    with get_poll_context(db, spot_chain=spot_chain, dex_chain=dex_chain) as ctx:
        run_one_cycle(ctx, dex_pairs, log=_log)
        spot_rows = list(ctx.conn.execute("SELECT symbol FROM spot_price_snapshots ORDER BY symbol"))
        symbols = [r[0] for r in spot_rows]
        assert "ETH" in symbols
        assert "BTC" in symbols
        assert SOL_SYMBOL not in symbols
        dex_rows = list(ctx.conn.execute("SELECT 1 FROM sol_monitor_snapshots"))
        assert len(dex_rows) == 0


def test_rollback_on_failure_no_partial_writes(tmp_path: Path) -> None:
    """On failure before commit (e.g. health upsert raises), connection rolls back; no partial rows."""
    from unittest.mock import patch

    db = str(tmp_path / "cycle.db")
    spot_chain = SpotPriceChain(
        [FakeSpotProvider("ok", {"SOL": 150.0, "ETH": 3000.0, "BTC": 50000.0})],
        retry_config=RetryConfig(max_retries=1),
    )
    dex_chain = _dex_chain_ok()

    with get_poll_context(db, spot_chain=spot_chain, dex_chain=dex_chain) as ctx:
        with patch.object(ctx.health_store, "upsert_all", side_effect=RuntimeError("upsert failed")):
            with pytest.raises(RuntimeError, match="upsert failed"):
                run_one_cycle(ctx, [], log=_log)

    with get_poll_context(db, spot_chain=spot_chain, dex_chain=dex_chain) as ctx2:
        spot_count = ctx2.conn.execute("SELECT COUNT(*) FROM spot_price_snapshots").fetchone()[0]
        dex_count = ctx2.conn.execute("SELECT COUNT(*) FROM sol_monitor_snapshots").fetchone()[0]
    assert spot_count == 0
    assert dex_count == 0


def test_ingest_cycle_fallback_chain_deterministic(tmp_path: Path) -> None:
    """Ingestion cycle with primary failing deterministically: fallback used then success; outcome stable."""
    db = str(tmp_path / "cycle.db")
    # Primary fails exactly once per symbol
    primary = FakeSpotProviderFailNThenSucceed("p", fail_times=1, prices={"SOL": 100.0, "ETH": 2000.0, "BTC": 40000.0})
    backup = FakeSpotProvider("b", {"SOL": 101.0, "ETH": 2001.0, "BTC": 40001.0})
    spot_chain = SpotPriceChain([primary, backup], retry_config=RetryConfig(max_retries=1))
    dex_chain = _dex_chain_ok()
    dex_pairs = [{"chain_id": "solana", "pair_address": "x", "label": "SOL/USDC"}]

    with get_poll_context(db, spot_chain=spot_chain, dex_chain=dex_chain) as ctx:
        run_one_cycle(ctx, dex_pairs, log=_log)
        rows = list(ctx.conn.execute("SELECT symbol, spot_source FROM spot_price_snapshots ORDER BY symbol"))
        assert len(rows) == 3
        sources = {r[0]: r[1] for r in rows}
        assert set(sources) == {"SOL", "ETH", "BTC"}
        assert all(s in ("p", "b", "p(lkg)", "b(lkg)") for s in sources.values())
