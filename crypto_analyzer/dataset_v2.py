"""
Dataset hash v2: content-addressed deterministic hash of logical content (rows + schema).
Research-visible tables only; excludes governance/registry. Never writes to DB except
optional cache (Phase 1: cache optional, default off).
Invariant: dataset_id_v2 changes iff canonicalized logical content of allowlisted tables changes.
"""

from __future__ import annotations

import hashlib
import sqlite3
import struct
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

# Research-visible tables only (exclude experiments, promotion_*, regime_*, sweep_*, schema_*)
DATASET_HASH_SCOPE_V2 = [
    "spot_price_snapshots",
    "sol_monitor_snapshots",
    "bars_1h",
    "bars_15min",
    "bars_5min",
    "universe_allowlist",
]

DATASET_HASH_EXCLUDES = [
    "experiments",
    "promotion_candidates",
    "promotion_events",
    "regime_runs",
    "regime_states",
    "sweep_families",
    "sweep_hypotheses",
    "schema_migrations",
    "schema_migrations_phase3",
    "schema_migrations_v2",
]

# Optional: tables without PK can use this for deterministic ordering (table -> list of column names)
TABLE_DETERMINISTIC_KEYS: Dict[str, List[str]] = {}

_TS_COLUMN_CANDIDATES = ["ts_utc", "ts", "timestamp"]

# Canonical NaN payload (8 bytes) for REAL; same across platforms
_CANONICAL_NAN_BYTES = struct.pack(">d", float("nan"))


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def _get_table_info(conn: sqlite3.Connection, table: str) -> List[Tuple[int, str, str, int, Optional[int], int]]:
    """Returns list of (cid, name, type, notnull, dflt_value, pk) per PRAGMA table_info."""
    cur = conn.execute(f"PRAGMA table_info([{table}])")
    rows = cur.fetchall()
    # sqlite3 returns (cid, name, type, notnull, dflt_value, pk)
    return [tuple(r) for r in rows]


def _schema_signature(conn: sqlite3.Connection, table: str) -> bytes:
    """Stable bytes from PRAGMA table_info: (name, type, notnull, dflt_value, pk_ordinal)."""
    info = _get_table_info(conn, table)
    parts: List[bytes] = []
    for cid, name, col_type, notnull, dflt_value, pk in info:
        parts.append(name.encode("utf-8"))
        parts.append((col_type or "").encode("utf-8"))
        parts.append(str(notnull).encode("utf-8"))
        parts.append((str(dflt_value) if dflt_value is not None else "").encode("utf-8"))
        parts.append(str(pk if pk else "").encode("utf-8"))
    return b"|".join(parts)


def _detect_ts_column(conn: sqlite3.Connection, table: str) -> Optional[str]:
    info = _get_table_info(conn, table)
    names = {row[1] for row in info}
    for c in _TS_COLUMN_CANDIDATES:
        if c in names:
            return c
    return None


def _get_pk_columns_ordered(conn: sqlite3.Connection, table: str) -> List[str]:
    """PK column names in pk ordinal order (for ORDER BY)."""
    info = _get_table_info(conn, table)
    pk_cols = [(row[4], row[1]) for row in info if row[5]]  # (pk_ordinal, name)
    pk_cols.sort(key=lambda x: x[0])
    return [name for _, name in pk_cols]


def _order_clause(conn: sqlite3.Connection, table: str) -> Tuple[str, str]:
    """
    Returns (ORDER BY clause fragment, ordering_mode).
    ordering_mode: "pk" | "deterministic_keys" | "ts_then_rowid" | "rowid_fallback"
    """
    pk_cols = _get_pk_columns_ordered(conn, table)
    if pk_cols:
        order_by = ", ".join(f"[{c}]" for c in pk_cols)
        return order_by, "pk"
    if table in TABLE_DETERMINISTIC_KEYS:
        keys = TABLE_DETERMINISTIC_KEYS[table]
        order_by = ", ".join(f"[{c}]" for c in keys)
        return order_by, "deterministic_keys"
    ts_col = _detect_ts_column(conn, table)
    if ts_col:
        # Use ts_col, rowid (rowid is always present in SQLite tables)
        return f"[{ts_col}], rowid", "ts_then_rowid"
    return "rowid", "rowid_fallback"


def _encode_cell(value: Any, declared_type: str) -> bytes:
    """Canonical encoding: NULL sentinel, int64 BE, float64 BE (canonical NaN), UTF-8 text, raw blob."""
    if value is None:
        return b"\x00"
    declared_upper = (declared_type or "").upper()
    if "INT" in declared_upper:
        try:
            v = int(value)
        except (TypeError, ValueError):
            v = int(value) if value is not None else 0
        if not (-(2**63) <= v < 2**63):
            raise OverflowError(f"Integer out of int64 range: {v}")
        return b"\x01" + struct.pack(">q", v)
    if "REAL" in declared_upper or "FLOAT" in declared_upper or "DOUBLE" in declared_upper:
        try:
            f = float(value)
        except (TypeError, ValueError):
            f = float("nan")
        if f != f:  # NaN
            return b"\x02" + _CANONICAL_NAN_BYTES
        return b"\x02" + struct.pack(">d", f)
    if "TEXT" in declared_upper or "CHAR" in declared_upper or "CLOB" in declared_upper:
        s = str(value) if value is not None else ""
        return b"\x03" + s.encode("utf-8")
    # BLOB or anything else: treat as bytes
    if isinstance(value, bytes):
        return b"\x04" + value
    return b"\x04" + str(value).encode("utf-8")


def _content_digest_table(conn: sqlite3.Connection, table: str) -> Tuple[bytes, str, Dict[str, Any]]:
    """
    Returns (content_digest_sha256_raw, ordering_mode, warnings_dict).
    Streams rows in deterministic order, canonical encoding per cell, then sha256.
    """
    info = _get_table_info(conn, table)
    if not info:
        return hashlib.sha256(b"").digest(), "empty", {}
    col_names = [row[1] for row in info]
    col_types = [row[2] for row in info]
    order_sql, ordering_mode = _order_clause(conn, table)
    warnings: Dict[str, Any] = {}
    if ordering_mode in ("ts_then_rowid", "rowid_fallback"):
        warnings["ordering_mode"] = ordering_mode
        warnings["ordering_warning"] = True

    hasher = hashlib.sha256()
    # Row encoding: col_count (fixed) then per column: col_name || declared_type || value_payload
    # Columns in cid order
    try:
        cur = conn.execute(f"SELECT [{'], ['.join(col_names)}] FROM [{table}] ORDER BY {order_sql}")
        for row in cur:
            hasher.update(struct.pack(">I", len(col_names)))
            for i, (name, ctype) in enumerate(zip(col_names, col_types)):
                val = row[i]
                hasher.update(name.encode("utf-8"))
                hasher.update((ctype or "").encode("utf-8"))
                payload = _encode_cell(val, ctype or "")
                hasher.update(struct.pack(">I", len(payload)))
                hasher.update(payload)
    except sqlite3.OperationalError:
        return hashlib.sha256(b"__table_missing_or_empty__").digest(), "error", {"error": "table inaccessible"}

    return hasher.digest(), ordering_mode, warnings


def _table_digest(conn: sqlite3.Connection, table: str) -> Tuple[str, Dict[str, Any]]:
    """Returns (table_digest_hex, metadata_for_table)."""
    schema_sig = _schema_signature(conn, table)
    content_digest, ordering_mode, warnings = _content_digest_table(conn, table)
    meta: Dict[str, Any] = {"ordering_mode": ordering_mode, **warnings}
    return hashlib.sha256(schema_sig + content_digest).hexdigest(), meta


def compute_dataset_id_v2(
    conn: sqlite3.Connection,
    *,
    scope: Optional[List[str]] = None,
    mode: Literal["STRICT", "FAST_DEV"] = "STRICT",
) -> Tuple[str, Dict[str, Any]]:
    """
    Compute dataset_id_v2 and metadata. Does not write to DB.

    scope: list of table names to include (default DATASET_HASH_SCOPE_V2).
    mode: STRICT or FAST_DEV (recorded in metadata; gatekeeper requires STRICT for promotion).

    Returns (dataset_id_v2_hex_prefix_16, metadata_dict).
    metadata_dict includes: dataset_hash_algo, dataset_hash_mode, dataset_hash_scope,
    dataset_hash_excludes, dataset_hash_created_utc, table_digests, warnings (e.g. rowid_fallback).
    """
    if scope is None:
        scope = list(DATASET_HASH_SCOPE_V2)
    created_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    table_digests_sorted: List[Tuple[str, str]] = []
    all_warnings: Dict[str, Any] = {}

    for table in sorted(scope):
        if not _table_exists(conn, table):
            continue
        tdigest_hex, tmeta = _table_digest(conn, table)
        table_digests_sorted.append((table, tdigest_hex))
        if tmeta.get("ordering_warning"):
            all_warnings[table] = tmeta

    concat = b"".join((t.encode("utf-8") + d.encode("utf-8") for t, d in table_digests_sorted))
    full_hash = hashlib.sha256(concat).hexdigest()
    dataset_id_v2 = full_hash[:16]

    metadata: Dict[str, Any] = {
        "dataset_hash_algo": "sqlite_logical_v2",
        "dataset_hash_mode": mode,
        "dataset_hash_scope": scope,
        "dataset_hash_excludes": DATASET_HASH_EXCLUDES,
        "dataset_hash_created_utc": created_utc,
        "table_digests": {t: d for t, d in table_digests_sorted},
    }
    if all_warnings:
        metadata["warnings"] = all_warnings
    return dataset_id_v2, metadata


def get_dataset_id_v2(db_path: str, *, mode: Literal["STRICT", "FAST_DEV"] = "STRICT") -> Tuple[str, Dict[str, Any]]:
    """Convenience: open DB at db_path, compute v2, return (dataset_id_v2, metadata)."""
    with sqlite3.connect(db_path) as conn:
        return compute_dataset_id_v2(conn, scope=list(DATASET_HASH_SCOPE_V2), mode=mode)


def backfill_dataset_id_v2(db_path: str) -> Tuple[str, Dict[str, Any]]:
    """
    Phase 1 backfill: compute dataset_id_v2 (STRICT) once, write to dataset_metadata and
    update experiments rows missing dataset_id_v2. Returns (dataset_id_v2, metadata).
    """
    import json as _json

    dataset_id_v2, metadata = get_dataset_id_v2(db_path, mode="STRICT")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dataset_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO dataset_metadata (key, value) VALUES (?, ?)",
            ("dataset_id_v2", dataset_id_v2),
        )
        conn.execute(
            "INSERT OR REPLACE INTO dataset_metadata (key, value) VALUES (?, ?)",
            ("dataset_hash_algo", metadata.get("dataset_hash_algo", "sqlite_logical_v2")),
        )
        conn.execute(
            "INSERT OR REPLACE INTO dataset_metadata (key, value) VALUES (?, ?)",
            ("dataset_hash_mode", metadata.get("dataset_hash_mode", "STRICT")),
        )
        conn.execute(
            "INSERT OR REPLACE INTO dataset_metadata (key, value) VALUES (?, ?)",
            ("dataset_hash_scope", _json.dumps(metadata.get("dataset_hash_scope", []))),
        )
        if metadata.get("warnings"):
            conn.execute(
                "INSERT OR REPLACE INTO dataset_metadata (key, value) VALUES (?, ?)",
                ("dataset_hash_warnings", _json.dumps(metadata["warnings"])),
            )
        conn.commit()
        try:
            cur = conn.execute("SELECT 1 FROM experiments LIMIT 1")
            if cur.fetchone():
                conn.execute(
                    """UPDATE experiments SET dataset_id_v2 = ?, dataset_hash_algo = ?, dataset_hash_mode = ?
                       WHERE dataset_id_v2 IS NULL OR dataset_id_v2 = ''""",
                    (
                        dataset_id_v2,
                        metadata.get("dataset_hash_algo", "sqlite_logical_v2"),
                        metadata.get("dataset_hash_mode", "STRICT"),
                    ),
                )
                conn.commit()
        except sqlite3.OperationalError:
            pass
    return dataset_id_v2, metadata
