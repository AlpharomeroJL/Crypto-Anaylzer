"""
Audit trace: query helper to retrieve all linked IDs and artifact hashes for an accepted candidate.
Phase 3.5 A4. Governance layer only; reads from store (SQLite).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AuditTrace:
    """All linked entities for a candidate acceptance: eligibility, governance events, artifact lineage."""

    candidate_id: str
    eligibility_report_id: Optional[str] = None
    governance_events: List[Dict[str, Any]] = field(default_factory=list)
    artifact_lineage: List[Dict[str, Any]] = field(default_factory=list)


def trace_acceptance(conn: sqlite3.Connection, candidate_id: str) -> AuditTrace:
    """
    Return an audit trace for the given candidate_id: eligibility report, governance events,
    and artifact_lineage rows that match the candidate's run (run_instance_id from evidence or run_id).
    """
    trace = AuditTrace(candidate_id=candidate_id)

    # Candidate row
    cur = conn.execute(
        "SELECT eligibility_report_id, run_id, evidence_json FROM promotion_candidates WHERE candidate_id = ?",
        (candidate_id,),
    )
    row = cur.fetchone()
    if not row:
        return trace
    trace.eligibility_report_id = row[0] or None
    run_instance_id = row[1] or ""
    if row[2]:
        try:
            ev = json.loads(row[2])
            run_instance_id = ev.get("run_instance_id") or ev.get("run_id") or run_instance_id
        except Exception:
            pass

    # Governance events for this candidate
    if _governance_events_exist(conn):
        cur = conn.execute(
            "SELECT event_id, timestamp, actor, action, candidate_id, eligibility_report_id, run_key, dataset_id_v2 FROM governance_events WHERE candidate_id = ? ORDER BY event_id",
            (candidate_id,),
        )
        cols = [d[0] for d in cur.description]
        trace.governance_events = [dict(zip(cols, r)) for r in cur.fetchall()]

    # Artifact lineage for this run_instance_id
    if _lineage_tables_exist(conn) and run_instance_id:
        cur = conn.execute(
            "SELECT artifact_id, run_instance_id, run_key, dataset_id_v2, artifact_type, relative_path, sha256, created_utc FROM artifact_lineage WHERE run_instance_id = ?",
            (run_instance_id,),
        )
        cols = [d[0] for d in cur.description]
        trace.artifact_lineage = [dict(zip(cols, r)) for r in cur.fetchall()]

    return trace


def _governance_events_exist(conn: sqlite3.Connection) -> bool:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='governance_events'")
    return cur.fetchone() is not None


def _lineage_tables_exist(conn: sqlite3.Connection) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('artifact_lineage', 'artifact_edges')"
    )
    names = {r[0] for r in cur.fetchall()}
    return names >= {"artifact_lineage"}
