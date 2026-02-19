"""
Ingestion API: poll context and one-cycle execution.

CLI must use this module instead of importing crypto_analyzer.db directly.
Owns DB writes, migrations, and provider chains internally.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..db.health import ProviderHealthStore
from ..db.migrations import run_migrations
from ..db.writer import DbWriter
from ..providers.base import ProviderStatus
from ..providers.defaults import create_default_registry, create_dex_chain, create_spot_chain

logger = logging.getLogger(__name__)

# Default spot assets: (symbol, Coinbase product, Kraken pair). Used by run_one_cycle.
SPOT_ASSETS = [
    ("SOL", "SOL-USD", "SOLUSD"),
    ("ETH", "ETH-USD", "ETHUSD"),
    ("BTC", "BTC-USD", "XBTUSD"),
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class PollContext:
    """Holds DB connection and provider chains for poll loop. Use as context manager or call close()."""

    conn: sqlite3.Connection
    db_writer: DbWriter
    health_store: ProviderHealthStore
    spot_chain: Any  # SpotPriceChain
    dex_chain: Any  # DexSnapshotChain
    _closed: bool = field(default=False, repr=False)

    def close(self) -> None:
        """Close the DB connection. Idempotent: safe to call multiple times."""
        if self._closed:
            return
        try:
            self.conn.close()
        finally:
            self._closed = True

    def __enter__(self) -> PollContext:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_val is not None:
            try:
                self.conn.rollback()
            except Exception:
                pass
        self.close()


def get_poll_context(db_path: str) -> PollContext:
    """
    Open DB, run migrations, create writer/health store and provider chains.
    Use as: with get_poll_context(db_path) as ctx: ...
    """
    conn = sqlite3.connect(db_path)
    run_migrations(conn, db_path)
    db_writer = DbWriter(conn)
    health_store = ProviderHealthStore(conn)
    registry = create_default_registry()
    spot_chain = create_spot_chain(registry)
    dex_chain = create_dex_chain(registry)
    return PollContext(
        conn=conn,
        db_writer=db_writer,
        health_store=health_store,
        spot_chain=spot_chain,
        dex_chain=dex_chain,
    )


def run_one_cycle(
    ctx: PollContext,
    dex_pairs: List[Dict[str, Any]],
    *,
    pair_delay: float = 0.0,
    log: logging.Logger | None = None,
) -> None:
    """
    Run one poll cycle: spot prices, DEX snapshots, write to DB, commit, persist health.
    On exception rolls back the connection and re-raises.
    Uses log for progress/warnings; if None, uses module logger.
    """
    _log = log if log is not None else logger
    ts = utc_now_iso()
    spot_quotes = []
    for symbol, _cb_product, _kraken_pair in SPOT_ASSETS:
        try:
            quote = ctx.spot_chain.get_spot(symbol)
            spot_quotes.append(quote)
        except Exception as e:
            _log.warning("spot %s: all providers failed: %s", symbol, e)

    try:
        sol_price = spot_quotes[0].price_usd if spot_quotes else 0.0
        for quote in spot_quotes:
            ctx.db_writer.write_spot_price(ts, quote)

        spot_details = []
        for q in spot_quotes:
            provider_tag = q.provider_name
            if q.status != ProviderStatus.OK:
                provider_tag += f"({q.status.value})"
            spot_details.append(f"{q.symbol}={q.price_usd:.2f}[{provider_tag}]")

        dex_summaries: List[str] = []
        for i, p in enumerate(dex_pairs):
            chain_id = p["chain_id"]
            pair_addr = p["pair_address"]
            label = p.get("label", "")
            try:
                snapshot = ctx.dex_chain.get_snapshot(chain_id, pair_addr)
                ctx.db_writer.write_dex_snapshot(
                    ts,
                    snapshot,
                    sol_price,
                    spot_source=spot_quotes[0].provider_name if spot_quotes else "unknown",
                )
                lbl = label or f"{snapshot.base_symbol}/{snapshot.quote_symbol}"
                dex_summaries.append(f"[{lbl} liq={snapshot.liquidity_usd} vol24={snapshot.vol_h24}]")
            except Exception as e:
                _log.warning("dex %s:%s: all providers failed: %s", chain_id, pair_addr, e)
            if i < len(dex_pairs) - 1 and pair_delay > 0:
                time.sleep(pair_delay)

        ctx.db_writer.commit()
        try:
            ctx.health_store.upsert_all(ctx.spot_chain.get_health())
            ctx.health_store.upsert_all(ctx.dex_chain.get_health())
        except Exception:
            pass

        spot_str = "  ".join(spot_details)
        dex_str = (
            f"  dex_pairs={len(dex_pairs)} " + " ".join(dex_summaries)
            if dex_summaries
            else f"  dex_pairs={len(dex_pairs)} (no ok)"
        )
        _log.info("%s  OK  %s%s", ts, spot_str, dex_str)
    except Exception:
        try:
            ctx.conn.rollback()
        except Exception:
            pass
        raise


def get_provider_health(db_path: str) -> List[Any]:
    """Load all provider health records for dashboard. Returns list of ProviderHealth."""
    conn = sqlite3.connect(db_path)
    try:
        run_migrations(conn, db_path)
        store = ProviderHealthStore(conn)
        return store.load_all()
    finally:
        conn.close()
