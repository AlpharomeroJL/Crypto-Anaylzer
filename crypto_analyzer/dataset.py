"""
Dataset versioning: fingerprint and deterministic dataset_id for reproducibility.
Research-only; no DB writes.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


KNOWN_TABLES = [
    "sol_monitor_snapshots",
    "spot_price_snapshots",
    "bars_1h",
    "bars_15min",
    "bars_5min",
    "universe_allowlist",
    "experiments",
]

_TS_COLUMN_CANDIDATES = ["ts_utc", "ts", "timestamp"]


@dataclass
class TableSummary:
    table: str
    row_count: int
    min_ts: Optional[str] = None
    max_ts: Optional[str] = None


@dataclass
class DatasetFingerprint:
    schema_version: str = "1"
    db_path: str = ""
    created_ts_utc: str = ""
    tables: List[TableSummary] = field(default_factory=list)
    integrity: Dict[str, Any] = field(default_factory=dict)


def _detect_ts_column(conn: sqlite3.Connection, table: str) -> Optional[str]:
    """Return the first ts-like column name found, or None."""
    try:
        cur = conn.execute(f"PRAGMA table_info([{table}])")
        cols = {row[1] for row in cur.fetchall()}
    except sqlite3.OperationalError:
        return None
    for candidate in _TS_COLUMN_CANDIDATES:
        if candidate in cols:
            return candidate
    return None


def _table_summary(conn: sqlite3.Connection, table: str) -> Optional[TableSummary]:
    """Build a TableSummary for one table, or None if the table doesn't exist."""
    try:
        cur = conn.execute(f"SELECT COUNT(*) FROM [{table}]")
        row_count = cur.fetchone()[0]
    except sqlite3.OperationalError:
        return None

    ts_col = _detect_ts_column(conn, table)
    min_ts: Optional[str] = None
    max_ts: Optional[str] = None
    if ts_col is not None:
        try:
            cur = conn.execute(
                f"SELECT MIN([{ts_col}]), MAX([{ts_col}]) FROM [{table}]"
            )
            row = cur.fetchone()
            if row:
                min_ts = row[0]
                max_ts = row[1]
        except sqlite3.OperationalError:
            pass
    return TableSummary(table=table, row_count=row_count, min_ts=min_ts, max_ts=max_ts)


def _integrity_summary(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Quick non-positive price counts (same checks doctor uses)."""
    checks = [
        ("spot_price_snapshots", "spot_price_usd"),
        ("sol_monitor_snapshots", "dex_price_usd"),
        ("bars_1h", "close"),
    ]
    result: Dict[str, Any] = {}
    for table, col in checks:
        try:
            cur = conn.execute(
                f"SELECT COUNT(*) FROM [{table}] WHERE [{col}] IS NOT NULL AND [{col}] <= 0"
            )
            bad = cur.fetchone()[0]
            cur2 = conn.execute(f"SELECT COUNT(*) FROM [{table}]")
            total = cur2.fetchone()[0]
            if total > 0:
                result[f"{table}.{col}"] = {
                    "bad": bad,
                    "total": total,
                    "rate": round(bad / total, 6) if total else 0,
                }
        except sqlite3.OperationalError:
            pass
    return result


def compute_dataset_fingerprint(
    db_path: str,
    tables: Optional[List[str]] = None,
) -> DatasetFingerprint:
    """Compute a read-only fingerprint of the dataset. Never writes to DB."""
    if tables is None:
        tables = list(KNOWN_TABLES)

    basename = os.path.basename(db_path)
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")

    fp = DatasetFingerprint(
        schema_version="1",
        db_path=basename,
        created_ts_utc=created,
    )

    if not os.path.isfile(db_path):
        return fp

    with sqlite3.connect(db_path) as conn:
        for t in tables:
            summary = _table_summary(conn, t)
            if summary is not None:
                fp.tables.append(summary)
        fp.integrity = _integrity_summary(conn)

    return fp


def _fingerprint_to_canonical_json(fp: DatasetFingerprint) -> str:
    """Stable canonical JSON for hashing (sorted keys, no created_ts_utc)."""
    d = asdict(fp)
    d.pop("created_ts_utc", None)
    return json.dumps(d, sort_keys=True, separators=(",", ":"))


def dataset_id_from_fingerprint(fp: DatasetFingerprint) -> str:
    """Deterministic SHA-256 hash (first 16 hex chars) of canonical fingerprint."""
    canonical = _fingerprint_to_canonical_json(fp)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def get_dataset_id(db_path: str) -> str:
    """Convenience: compute fingerprint and return its dataset_id."""
    fp = compute_dataset_fingerprint(db_path)
    return dataset_id_from_fingerprint(fp)


def fingerprint_to_json(fp: DatasetFingerprint) -> str:
    """Human-readable compact JSON (includes created_ts_utc)."""
    return json.dumps(asdict(fp), sort_keys=True, separators=(", ", ": "))
