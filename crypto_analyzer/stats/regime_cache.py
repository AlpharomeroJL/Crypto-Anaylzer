"""
Regime materialization cache: validate DB hit before skipping compute.
Phase 3 PR3. Rowcount + metadata invariants; no silent reuse.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, Optional


def regime_run_exists(conn: sqlite3.Connection, regime_run_id: str) -> Optional[Dict[str, Any]]:
    """Return regime_runs row as dict if exists, else None."""
    cur = conn.execute(
        "SELECT regime_run_id, dataset_id, freq, model, params_json FROM regime_runs WHERE regime_run_id = ?",
        (regime_run_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "regime_run_id": row[0],
        "dataset_id": row[1],
        "freq": row[2],
        "model": row[3],
        "params_json": row[4],
    }


def regime_run_matches_invocation(
    row: Dict[str, Any],
    dataset_id: str,
    freq: str,
    model: str,
    params_json: Optional[str],
) -> bool:
    """True if stored metadata matches this invocation."""
    if row is None:
        return False
    if row.get("dataset_id") != dataset_id:
        return False
    if row.get("freq") != freq:
        return False
    if row.get("model") != model:
        return False
    stored_params = row.get("params_json")
    if stored_params != params_json:
        if stored_params is None and params_json is None:
            pass
        elif stored_params is None or params_json is None:
            return False
        else:
            try:
                if json.loads(stored_params) != json.loads(params_json):
                    return False
            except (json.JSONDecodeError, TypeError):
                return False
    return True


def regime_states_rowcount_match(
    conn: sqlite3.Connection,
    regime_run_id: str,
    expected_count: int,
) -> bool:
    """True if regime_states row count for this run matches expected."""
    cur = conn.execute(
        "SELECT COUNT(*) FROM regime_states WHERE regime_run_id = ?", (regime_run_id,)
    )
    got = cur.fetchone()[0]
    return got == expected_count
