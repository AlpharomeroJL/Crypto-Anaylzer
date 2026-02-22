"""
Governance event log persistence: append-only governance_events.
Phase 3 A3. Store layer only; no business logic.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional


def governance_events_table_exists(conn: sqlite3.Connection) -> bool:
    """Return True if governance_events table exists."""
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='governance_events'")
    return cur.fetchone() is not None


def append_governance_event(
    conn: sqlite3.Connection,
    *,
    timestamp: str,
    actor: str,
    action: str,
    candidate_id: Optional[str] = None,
    eligibility_report_id: Optional[str] = None,
    run_key: Optional[str] = None,
    dataset_id_v2: Optional[str] = None,
    artifact_refs: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Append one row to governance_events. Fails if table does not exist."""
    if not governance_events_table_exists(conn):
        raise RuntimeError("governance_events table not found; run Phase 3 migrations 011+")
    artifact_refs_json = json.dumps(artifact_refs, sort_keys=True) if artifact_refs else None
    conn.execute(
        """
        INSERT INTO governance_events (
            timestamp, actor, action, candidate_id, eligibility_report_id,
            run_key, dataset_id_v2, artifact_refs_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            timestamp,
            actor,
            action,
            candidate_id or "",
            eligibility_report_id or "",
            run_key or "",
            dataset_id_v2 or "",
            artifact_refs_json or "",
        ),
    )
    conn.commit()
