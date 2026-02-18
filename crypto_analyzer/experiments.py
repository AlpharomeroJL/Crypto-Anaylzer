"""
Experiment registry backed by SQLite. Persists run metadata, metrics, and artifacts
so runs can be compared over time. Complements (does not replace) JSON manifest flow.
Research-only.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experiments (
    run_id          TEXT PRIMARY KEY,
    ts_utc          TEXT NOT NULL,
    git_commit      TEXT,
    spec_version    TEXT,
    out_dir         TEXT,
    notes           TEXT,
    data_start      TEXT,
    data_end        TEXT,
    config_hash     TEXT,
    env_fingerprint TEXT,
    hypothesis      TEXT,
    tags_json       TEXT,
    dataset_id      TEXT,
    params_json     TEXT
);

CREATE TABLE IF NOT EXISTS experiment_metrics (
    run_id       TEXT NOT NULL,
    metric_name  TEXT NOT NULL,
    metric_value REAL,
    PRIMARY KEY (run_id, metric_name),
    FOREIGN KEY (run_id) REFERENCES experiments(run_id)
);

CREATE TABLE IF NOT EXISTS experiment_artifacts (
    run_id        TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    sha256        TEXT,
    PRIMARY KEY (run_id, artifact_path),
    FOREIGN KEY (run_id) REFERENCES experiments(run_id)
);
"""


_MIGRATION_COLUMNS = [
    ("hypothesis", "TEXT"),
    ("tags_json", "TEXT"),
    ("dataset_id", "TEXT"),
    ("params_json", "TEXT"),
]


def _migrate_experiment_tables(conn: sqlite3.Connection) -> None:
    """Add new columns to older experiment databases that lack them."""
    for col_name, col_type in _MIGRATION_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE experiments ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass


def ensure_experiment_tables(conn: sqlite3.Connection) -> None:
    """Create experiment registry tables if they do not exist."""
    conn.executescript(_SCHEMA_SQL)
    _migrate_experiment_tables(conn)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def record_experiment_run(
    db_path: str | Path,
    experiment_row: Dict[str, Any],
    metrics_dict: Optional[Dict[str, float]] = None,
    artifacts_list: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Insert (or upsert) one experiment run with its metrics and artifacts.

    experiment_row must contain at least ``run_id`` and ``ts_utc``.
    metrics_dict: {metric_name: metric_value}
    artifacts_list: [{"artifact_path": ..., "sha256": ...}, ...]

    Returns the run_id.
    """
    db_path = str(db_path)
    run_id = experiment_row["run_id"]

    with sqlite3.connect(db_path) as conn:
        ensure_experiment_tables(conn)

        tags_raw = experiment_row.get("tags_json")
        if isinstance(tags_raw, list):
            tags_raw = json.dumps(tags_raw)

        params_raw = experiment_row.get("params_json")
        if isinstance(params_raw, dict):
            params_raw = json.dumps(params_raw)

        conn.execute(
            """INSERT OR REPLACE INTO experiments
               (run_id, ts_utc, git_commit, spec_version, out_dir, notes,
                data_start, data_end, config_hash, env_fingerprint,
                hypothesis, tags_json, dataset_id, params_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                experiment_row.get("ts_utc", ""),
                experiment_row.get("git_commit", ""),
                experiment_row.get("spec_version", ""),
                experiment_row.get("out_dir", ""),
                experiment_row.get("notes", ""),
                experiment_row.get("data_start", ""),
                experiment_row.get("data_end", ""),
                experiment_row.get("config_hash", ""),
                experiment_row.get("env_fingerprint", ""),
                experiment_row.get("hypothesis"),
                tags_raw,
                experiment_row.get("dataset_id"),
                params_raw,
            ),
        )

        if metrics_dict:
            for mname, mval in metrics_dict.items():
                try:
                    val = float(mval) if mval is not None else None
                except (TypeError, ValueError):
                    val = None
                conn.execute(
                    """INSERT OR REPLACE INTO experiment_metrics
                       (run_id, metric_name, metric_value) VALUES (?, ?, ?)""",
                    (run_id, str(mname), val),
                )

        if artifacts_list:
            for art in artifacts_list:
                conn.execute(
                    """INSERT OR REPLACE INTO experiment_artifacts
                       (run_id, artifact_path, sha256) VALUES (?, ?, ?)""",
                    (run_id, art.get("artifact_path", ""), art.get("sha256", "")),
                )

    return run_id


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def load_experiments(db_or_dir: str | Path, limit: int = 200) -> pd.DataFrame:
    """
    Load experiment rows.

    If db_or_dir is a directory, falls back to legacy CSV loading (experiments.csv).
    If db_or_dir is a .db / .sqlite file, reads from the SQLite registry.
    """
    p = str(db_or_dir)
    if os.path.isdir(p):
        csv_path = os.path.join(p, "experiments.csv")
        if not os.path.isfile(csv_path):
            return pd.DataFrame()
        return pd.read_csv(csv_path)
    if not os.path.isfile(p):
        return pd.DataFrame()
    try:
        with sqlite3.connect(p) as conn:
            ensure_experiment_tables(conn)
            df = pd.read_sql_query(
                "SELECT * FROM experiments ORDER BY ts_utc DESC LIMIT ?",
                conn,
                params=(limit,),
            )
        return df
    except Exception:
        return pd.DataFrame()


def load_experiment_metrics(db_path: str | Path, run_id: str) -> pd.DataFrame:
    """Load metrics for a single run_id."""
    db_path = str(db_path)
    if not os.path.isfile(db_path):
        return pd.DataFrame()
    try:
        with sqlite3.connect(db_path) as conn:
            ensure_experiment_tables(conn)
            df = pd.read_sql_query(
                "SELECT * FROM experiment_metrics WHERE run_id = ?",
                conn,
                params=(run_id,),
            )
        return df
    except Exception:
        return pd.DataFrame()


def load_metric_history(
    db_path: str | Path, metric_name: str, limit: int = 500
) -> pd.DataFrame:
    """Load metric_value over time for a given metric_name across all runs."""
    db_path = str(db_path)
    if not os.path.isfile(db_path):
        return pd.DataFrame()
    try:
        with sqlite3.connect(db_path) as conn:
            ensure_experiment_tables(conn)
            df = pd.read_sql_query(
                """SELECT m.run_id, e.ts_utc, m.metric_name, m.metric_value
                   FROM experiment_metrics m
                   JOIN experiments e ON m.run_id = e.run_id
                   WHERE m.metric_name = ?
                   ORDER BY e.ts_utc DESC
                   LIMIT ?""",
                conn,
                params=(metric_name, limit),
            )
        return df
    except Exception:
        return pd.DataFrame()


def load_distinct_metric_names(db_path: str | Path) -> List[str]:
    """Return sorted list of distinct metric names in the registry."""
    db_path = str(db_path)
    if not os.path.isfile(db_path):
        return []
    try:
        with sqlite3.connect(db_path) as conn:
            ensure_experiment_tables(conn)
            cur = conn.execute("SELECT DISTINCT metric_name FROM experiment_metrics ORDER BY metric_name")
            return [row[0] for row in cur.fetchall()]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Helpers – tag parsing and filtered loading
# ---------------------------------------------------------------------------

def parse_tags(s: str) -> list[str]:
    """Split a comma-separated tag string into a cleaned list."""
    if not s:
        return []
    return [t.strip() for t in s.split(",") if t.strip()]


def load_experiments_filtered(
    db_path: str | Path,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 200,
) -> pd.DataFrame:
    """Load experiments with optional tag / hypothesis filters."""
    db_path = str(db_path)
    if not os.path.isfile(db_path):
        return pd.DataFrame()
    try:
        with sqlite3.connect(db_path) as conn:
            ensure_experiment_tables(conn)
            clauses: list[str] = []
            params: list[Any] = []
            if tag:
                clauses.append("tags_json LIKE ?")
                params.append(f'%"{tag}"%')
            if search:
                clauses.append("hypothesis LIKE ?")
                params.append(f"%{search}%")
            where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
            query = f"SELECT * FROM experiments{where} ORDER BY ts_utc DESC LIMIT ?"
            params.append(limit)
            return pd.read_sql_query(query, conn, params=params)
    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Legacy compatibility – keep log_experiment / load_experiments(dir) working
# ---------------------------------------------------------------------------

def _git_hash() -> Optional[str]:
    try:
        import subprocess
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))) or ".",
        )
        return (r.stdout or "").strip() or None
    except Exception:
        return None


def log_experiment(
    run_name: str,
    config_dict: Dict[str, Any],
    metrics_dict: Dict[str, Any],
    artifacts_paths: Optional[List[str]] = None,
    out_dir: str = "reports/experiments",
) -> str:
    """
    Legacy experiment logger: writes JSON + appends to experiments.csv.
    Kept for backward compatibility with existing callers.
    """
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    git = _git_hash()
    payload = {
        "run_name": run_name,
        "timestamp": ts,
        "git_commit": git,
        "config": config_dict,
        "metrics": metrics_dict,
        "artifacts": list(artifacts_paths or []),
    }

    def _enc(o: Any) -> Any:
        if isinstance(o, dict):
            return {str(k): _enc(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_enc(x) for x in o]
        if isinstance(o, (pd.Timestamp, datetime)):
            return o.isoformat()
        if hasattr(o, "item") and callable(o.item):
            try:
                return o.item()
            except Exception:
                return str(o)
        if isinstance(o, (float, int, str, bool, type(None))):
            return o
        return str(o)

    payload_enc = _enc(payload)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in run_name)[:80]
    fname = f"{safe_name}_{ts[:19].replace(':', '-')}.json"
    path = os.path.join(out_dir, fname)
    with open(path, "w") as f:
        json.dump(payload_enc, f, indent=2)
    csv_path = os.path.join(out_dir, "experiments.csv")
    row = {
        "run_name": run_name,
        "timestamp": ts,
        "git_commit": git or "",
        **{f"metric_{k}": v for k, v in (metrics_dict or {}).items()},
    }
    df_row = pd.DataFrame([row])
    if os.path.isfile(csv_path):
        df_row.to_csv(csv_path, mode="a", header=False, index=False)
    else:
        df_row.to_csv(csv_path, mode="w", header=True, index=False)
    return path
