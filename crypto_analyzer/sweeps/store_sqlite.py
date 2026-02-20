"""
Sweep registry persistence: sweep_families and sweep_hypotheses (Phase 3).
Opt-in: only when run_migrations_phase3 has been applied to the DB.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from crypto_analyzer.timeutils import now_utc_iso


def sweep_registry_tables_exist(conn: sqlite3.Connection) -> bool:
    """Return True if sweep_families and sweep_hypotheses exist (Phase 3 applied)."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('sweep_families', 'sweep_hypotheses')"
    )
    names = {row[0] for row in cur.fetchall()}
    return names == {"sweep_families", "sweep_hypotheses"}


def persist_sweep_family(
    conn: sqlite3.Connection,
    *,
    family_id: str,
    dataset_id: str,
    sweep_payload_json: str,
    run_id: Optional[str] = None,
    sweep_name: Optional[str] = None,
    git_commit: Optional[str] = None,
    config_hash: Optional[str] = None,
    created_at_utc: Optional[str] = None,
    hypotheses: List[Dict[str, Any]],
) -> bool:
    """
    Persist one sweep family and its hypotheses. No-op if sweep tables do not exist.
    hypotheses: list of dicts with keys hypothesis_id, signal_name, horizon, estimator (optional),
                params_json (optional), regime_run_id (optional).
    Returns True if rows were inserted, False if tables missing (opt-in).
    """
    if not sweep_registry_tables_exist(conn):
        return False
    created = created_at_utc or now_utc_iso()
    conn.execute(
        """
        INSERT OR REPLACE INTO sweep_families (
            family_id, created_at_utc, dataset_id, run_id, sweep_name,
            sweep_payload_json, git_commit, config_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            family_id,
            created,
            dataset_id,
            run_id,
            sweep_name,
            sweep_payload_json,
            git_commit,
            config_hash,
        ),
    )
    for h in hypotheses:
        conn.execute(
            """
            INSERT OR REPLACE INTO sweep_hypotheses (
                family_id, hypothesis_id, signal_name, horizon, estimator, params_json, regime_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                family_id,
                h["hypothesis_id"],
                h["signal_name"],
                int(h["horizon"]),
                h.get("estimator"),
                h.get("params_json"),
                h.get("regime_run_id"),
            ),
        )
    conn.commit()
    return True
