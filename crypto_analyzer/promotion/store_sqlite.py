"""
Promotion store: SQLite persistence for promotion_candidates and promotion_events.
Phase 3 Slice 5. Requires run_migrations_phase3 to be applied.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from crypto_analyzer.timeutils import now_utc_iso

PROMOTION_TABLES_REQUIRED_MSG = (
    "Promotion tables not found. Run Phase 3 migrations to create them: "
    "run_migrations_phase3(conn, db_path). From CLI: python cli/promotion.py init --db <path>"
)


def promotion_tables_exist(conn: sqlite3.Connection) -> bool:
    """Return True if promotion_candidates and promotion_events exist."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('promotion_candidates', 'promotion_events')"
    )
    names = {row[0] for row in cur.fetchall()}
    return names == {"promotion_candidates", "promotion_events"}


def require_promotion_tables(conn: sqlite3.Connection) -> None:
    """Raise RuntimeError with clear message if promotion tables are missing."""
    if not promotion_tables_exist(conn):
        raise RuntimeError(PROMOTION_TABLES_REQUIRED_MSG)


def init_promotion_tables(db_path: Union[str, Path]) -> None:
    """Run Phase 3 migrations to create promotion (and regime) tables. Opt-in. Call from CLI or UI."""
    from crypto_analyzer.db.migrations_phase3 import run_migrations_phase3

    path = str(Path(db_path).resolve())
    conn = sqlite3.connect(path)
    try:
        run_migrations_phase3(conn, path)
    finally:
        conn.close()


def _canonical_json(obj: Any, float_round: int = 10) -> Any:
    """Encode for deterministic JSON: sorted keys, rounded floats."""
    if isinstance(obj, dict):
        return {str(k): _canonical_json(v, float_round) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [_canonical_json(x, float_round) for x in obj]
    if isinstance(obj, float):
        return round(obj, float_round) if obj == obj else None
    if isinstance(obj, (int, str, bool, type(None))):
        return obj
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def _relativize_evidence_paths(evidence: Dict[str, Any], base: Optional[Path]) -> Dict[str, Any]:
    """Make path-like values in evidence relative to base where possible. Returns copy."""
    if base is None:
        return evidence
    base_str = str(Path(base).resolve())
    out: Dict[str, Any] = {}
    for k, v in evidence.items():
        if isinstance(v, str) and os.path.isabs(v):
            try:
                rel = os.path.relpath(os.path.normpath(v), base_str)
                if not rel.startswith(".."):
                    out[k] = rel
                else:
                    out[k] = v
            except (ValueError, OSError):
                out[k] = v
        elif isinstance(v, dict):
            out[k] = _relativize_evidence_paths(v, base)
        elif isinstance(v, list):
            out[k] = [_relativize_evidence_paths(x, base) if isinstance(x, dict) else x for x in v]
        else:
            out[k] = v
    return out


def _evidence_to_json(evidence: Dict[str, Any], float_round: int = 10) -> str:
    """Serialize evidence dict to deterministic JSON (sort_keys + stable float rounding)."""
    encoded = _canonical_json(evidence, float_round=float_round)
    return json.dumps(encoded, sort_keys=True)


def _make_candidate_id(run_id: str, signal_name: str, horizon: int, created_at_utc: str) -> str:
    """Stable candidate_id from run_id + signal + horizon + created_at."""
    payload = f"{run_id}|{signal_name}|{horizon}|{created_at_utc}"
    h = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"prom_{h[:16]}"


def create_candidate(
    conn: sqlite3.Connection,
    *,
    dataset_id: str,
    run_id: str,
    signal_name: str,
    horizon: int,
    config_hash: str,
    git_commit: str,
    family_id: Optional[str] = None,
    estimator: Optional[str] = None,
    notes: Optional[str] = None,
    evidence: Optional[Dict[str, Any]] = None,
    status: str = "exploratory",
    candidate_id: Optional[str] = None,
    evidence_base_path: Optional[Union[str, Path]] = None,
) -> str:
    """
    Insert a promotion candidate. Returns candidate_id.
    If candidate_id not provided, generates from run_id|signal_name|horizon|created_at_utc.
    If evidence_base_path is set, paths in evidence are stored relative to it where possible.
    """
    require_promotion_tables(conn)
    created_at_utc = now_utc_iso()
    if candidate_id is None:
        candidate_id = _make_candidate_id(run_id, signal_name, horizon, created_at_utc)
    if evidence:
        evidence = _relativize_evidence_paths(evidence, Path(evidence_base_path) if evidence_base_path else None)
    evidence_json = _evidence_to_json(evidence) if evidence else None
    conn.execute(
        """
        INSERT INTO promotion_candidates (
            candidate_id, created_at_utc, status, dataset_id, run_id, family_id,
            signal_name, horizon, estimator, config_hash, git_commit, notes, evidence_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            candidate_id,
            created_at_utc,
            status,
            dataset_id,
            run_id,
            family_id,
            signal_name,
            horizon,
            estimator,
            config_hash,
            git_commit,
            notes,
            evidence_json,
        ),
    )
    conn.commit()
    record_event(conn, candidate_id, "created", {"created_at_utc": created_at_utc})
    return candidate_id


def update_status(
    conn: sqlite3.Connection,
    candidate_id: str,
    status: str,
    reason: Optional[str] = None,
) -> None:
    """Update candidate status and record status_change event."""
    require_promotion_tables(conn)
    conn.execute(
        "UPDATE promotion_candidates SET status = ? WHERE candidate_id = ?",
        (status, candidate_id),
    )
    conn.commit()
    payload: Dict[str, Any] = {"new_status": status, "ts_utc": now_utc_iso()}
    if reason is not None:
        payload["reason"] = reason
    record_event(conn, candidate_id, "status_change", payload)


def record_event(
    conn: sqlite3.Connection,
    candidate_id: str,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    """Append an audit event for the candidate."""
    require_promotion_tables(conn)
    ts_utc = now_utc_iso()
    payload_json = json.dumps(_canonical_json(payload or {}), sort_keys=True) if payload else None
    conn.execute(
        "INSERT INTO promotion_events (candidate_id, ts_utc, event_type, payload_json) VALUES (?, ?, ?, ?)",
        (candidate_id, ts_utc, event_type, payload_json),
    )
    conn.commit()


def list_candidates(
    conn: sqlite3.Connection,
    status: Optional[str] = None,
    dataset_id: Optional[str] = None,
    signal_name: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """List candidates with optional filters. Returns list of row dicts."""
    require_promotion_tables(conn)
    q = "SELECT * FROM promotion_candidates WHERE 1=1"
    params: List[Any] = []
    if status is not None:
        q += " AND status = ?"
        params.append(status)
    if dataset_id is not None:
        q += " AND dataset_id = ?"
        params.append(dataset_id)
    if signal_name is not None:
        q += " AND signal_name = ?"
        params.append(signal_name)
    q += " ORDER BY created_at_utc DESC LIMIT ?"
    params.append(limit)
    cur = conn.execute(q, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_candidate(conn: sqlite3.Connection, candidate_id: str) -> Optional[Dict[str, Any]]:
    """Return candidate row as dict or None."""
    require_promotion_tables(conn)
    cur = conn.execute("SELECT * FROM promotion_candidates WHERE candidate_id = ?", (candidate_id,))
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def get_events(conn: sqlite3.Connection, candidate_id: str) -> List[Dict[str, Any]]:
    """Return events for candidate in ascending event_id order."""
    require_promotion_tables(conn)
    cur = conn.execute(
        "SELECT event_id, candidate_id, ts_utc, event_type, payload_json FROM promotion_events WHERE candidate_id = ? ORDER BY event_id ASC",
        (candidate_id,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
