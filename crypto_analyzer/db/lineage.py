"""
Artifact lineage persistence: append-only artifact_lineage and artifact_edges.
Phase 3 A4. Store layer only; no business logic.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, Optional


def lineage_tables_exist(conn: sqlite3.Connection) -> bool:
    """Return True if artifact_lineage and artifact_edges exist."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('artifact_lineage', 'artifact_edges')"
    )
    names = {row[0] for row in cur.fetchall()}
    return names == {"artifact_lineage", "artifact_edges"}


def write_artifact_lineage(
    conn: sqlite3.Connection,
    *,
    artifact_id: str,
    run_instance_id: Optional[str] = None,
    run_key: Optional[str] = None,
    dataset_id_v2: Optional[str] = None,
    artifact_type: str,
    relative_path: Optional[str] = None,
    sha256: str,
    created_utc: str,
    engine_version: Optional[str] = None,
    config_version: Optional[str] = None,
    schema_versions: Optional[Dict[str, Any]] = None,
    plugin_manifest: Optional[Dict[str, Any]] = None,
) -> None:
    """Insert one row into artifact_lineage. Fails if tables do not exist or on constraint."""
    import json

    schema_versions_json = json.dumps(schema_versions, sort_keys=True) if schema_versions else None
    plugin_manifest_json = json.dumps(plugin_manifest, sort_keys=True) if plugin_manifest else None
    conn.execute(
        """
        INSERT INTO artifact_lineage (
            artifact_id, run_instance_id, run_key, dataset_id_v2, artifact_type,
            relative_path, sha256, created_utc, engine_version, config_version,
            schema_versions_json, plugin_manifest_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            artifact_id,
            run_instance_id or "",
            run_key or "",
            dataset_id_v2 or "",
            artifact_type,
            relative_path or "",
            sha256,
            created_utc,
            engine_version or "",
            config_version or "",
            schema_versions_json or "",
            plugin_manifest_json or "",
        ),
    )
    conn.commit()


def write_artifact_edge(
    conn: sqlite3.Connection,
    *,
    child_artifact_id: str,
    parent_artifact_id: str,
    relation: str,
) -> None:
    """Insert one row into artifact_edges. Relation: derived_from, uses_null, uses_folds, uses_transforms, uses_config."""
    conn.execute(
        "INSERT INTO artifact_edges (child_artifact_id, parent_artifact_id, relation) VALUES (?, ?, ?)",
        (child_artifact_id, parent_artifact_id, relation),
    )
    conn.commit()
