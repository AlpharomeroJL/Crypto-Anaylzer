"""
Shared database writer with provenance tracking.

All ingestion writes go through this layer to ensure:
1. Every record has provider_name, fetched_at_utc, fetch_status
2. Data quality gates reject invalid records before writing
3. Consistent error handling and logging
"""

from __future__ import annotations

import logging
import sqlite3
from typing import List

from ..providers.base import DexSnapshot, ProviderStatus, SpotQuote

logger = logging.getLogger(__name__)


class DbWriter:
    """Centralized database write layer with provenance and quality gates."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def write_spot_price(self, ts_utc: str, quote: SpotQuote) -> bool:
        """
        Write a spot price record with full provenance.
        Returns True if the record was written, False if rejected by quality gate.
        """
        if not quote.is_valid() and quote.status == ProviderStatus.DOWN:
            logger.warning(
                "Rejected spot write for %s: status=%s price=%s",
                quote.symbol,
                quote.status.value,
                quote.price_usd,
            )
            return False

        self._conn.execute(
            """
            INSERT INTO spot_price_snapshots
                (ts_utc, symbol, spot_price_usd, spot_source,
                 provider_name, fetched_at_utc, fetch_status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                ts_utc,
                quote.symbol,
                quote.price_usd,
                quote.provider_name,
                quote.provider_name,
                quote.fetched_at_utc,
                quote.status.value,
                quote.error_message,
            ),
        )
        return True

    def write_dex_snapshot(
        self,
        ts_utc: str,
        snapshot: DexSnapshot,
        spot_price_usd: float,
        spot_source: str,
    ) -> bool:
        """
        Write a DEX snapshot record with full provenance.
        Returns True if the record was written, False if rejected.
        """
        if not snapshot.is_valid() and snapshot.status == ProviderStatus.DOWN:
            logger.warning(
                "Rejected DEX write for %s:%s: status=%s",
                snapshot.chain_id,
                snapshot.pair_address,
                snapshot.status.value,
            )
            return False

        self._conn.execute(
            """
            INSERT INTO sol_monitor_snapshots (
                ts_utc, chain_id, pair_address, dex_id,
                base_symbol, quote_symbol,
                dex_price_usd, dex_price_native,
                liquidity_usd, vol_h24, txns_h24_buys, txns_h24_sells,
                spot_source, spot_price_usd, raw_pair_json,
                provider_name, fetched_at_utc, fetch_status, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                ts_utc,
                snapshot.chain_id,
                snapshot.pair_address,
                snapshot.dex_id,
                snapshot.base_symbol,
                snapshot.quote_symbol,
                snapshot.dex_price_usd,
                snapshot.dex_price_native,
                snapshot.liquidity_usd,
                snapshot.vol_h24,
                snapshot.txns_h24_buys,
                snapshot.txns_h24_sells,
                spot_source,
                spot_price_usd,
                snapshot.raw_json,
                snapshot.provider_name,
                snapshot.fetched_at_utc,
                snapshot.status.value,
                snapshot.error_message,
            ),
        )
        return True

    def write_spot_prices_batch(self, ts_utc: str, quotes: List[SpotQuote]) -> int:
        """Write multiple spot prices. Returns count of successfully written."""
        written = 0
        for quote in quotes:
            if self.write_spot_price(ts_utc, quote):
                written += 1
        return written

    def commit(self) -> None:
        self._conn.commit()
