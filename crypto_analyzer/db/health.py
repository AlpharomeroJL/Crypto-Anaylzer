"""
Provider health persistence in SQLite.

Tracks last success time, failure counts, and error messages per provider
so the dashboard can display real-time provider status.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ..providers.base import ProviderHealth, ProviderStatus

logger = logging.getLogger(__name__)


class ProviderHealthStore:
    """Read/write provider health records from SQLite."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, health: ProviderHealth) -> None:
        """Insert or update a provider's health record."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._conn.execute(
            """
            INSERT INTO provider_health
                (provider_name, status, last_ok_at, fail_count,
                 disabled_until, last_error, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider_name) DO UPDATE SET
                status = excluded.status,
                last_ok_at = excluded.last_ok_at,
                fail_count = excluded.fail_count,
                disabled_until = excluded.disabled_until,
                last_error = excluded.last_error,
                updated_at = excluded.updated_at;
            """,
            (
                health.provider_name,
                health.status.value,
                health.last_ok_at,
                health.fail_count,
                health.disabled_until,
                health.last_error,
                now,
            ),
        )
        self._conn.commit()

    def upsert_all(self, health_map: Dict[str, ProviderHealth]) -> None:
        """Batch upsert all provider health records."""
        for h in health_map.values():
            self.upsert(h)

    def load_all(self) -> List[ProviderHealth]:
        """Load all provider health records."""
        try:
            cur = self._conn.execute(
                "SELECT provider_name, status, last_ok_at, fail_count, "
                "disabled_until, last_error FROM provider_health"
            )
            results = []
            for row in cur.fetchall():
                results.append(ProviderHealth(
                    provider_name=row[0],
                    status=ProviderStatus(row[1]) if row[1] else ProviderStatus.OK,
                    last_ok_at=row[2],
                    fail_count=row[3] or 0,
                    last_error=row[5],
                    disabled_until=row[4],
                ))
            return results
        except sqlite3.OperationalError:
            return []

    def load_as_dict(self) -> Dict[str, ProviderHealth]:
        """Load all health records as a dict keyed by provider_name."""
        return {h.provider_name: h for h in self.load_all()}

    def get_freshness_seconds(self, provider_name: str) -> Optional[float]:
        """Seconds since last successful fetch for a provider."""
        try:
            cur = self._conn.execute(
                "SELECT last_ok_at FROM provider_health WHERE provider_name = ?",
                (provider_name,),
            )
            row = cur.fetchone()
            if not row or not row[0]:
                return None
            last_ok = datetime.fromisoformat(row[0])
            if last_ok.tzinfo is None:
                last_ok = last_ok.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            return (now - last_ok).total_seconds()
        except Exception:
            return None
