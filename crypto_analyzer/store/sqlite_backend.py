"""
SQLite backend: read_table from SQLite; lineage writes to SQLite.
Phase 3 A5. Default backend; authoritative for governance and lineage.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from crypto_analyzer.db.lineage import write_artifact_edge as _write_artifact_edge
from crypto_analyzer.db.lineage import write_artifact_lineage as _write_artifact_lineage


class SQLiteBackend:
    """Backend using SQLite for all reads and lineage writes."""

    def read_table(
        self,
        table: str,
        *,
        db_path: Optional[Union[str, Path]] = None,
        columns: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        if db_path is None:
            raise ValueError("SQLiteBackend.read_table requires db_path")
        db_path = str(Path(db_path).resolve())
        conn = sqlite3.connect(db_path)
        try:
            cols = ", ".join(columns) if columns else "*"
            q = f"SELECT {cols} FROM {table}"
            if limit is not None:
                q += f" LIMIT {limit}"
            return pd.read_sql_query(q, conn)
        finally:
            conn.close()

    def write_artifact_lineage(
        self,
        conn: Any,
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
        _write_artifact_lineage(
            conn,
            artifact_id=artifact_id,
            run_instance_id=run_instance_id,
            run_key=run_key,
            dataset_id_v2=dataset_id_v2,
            artifact_type=artifact_type,
            relative_path=relative_path,
            sha256=sha256,
            created_utc=created_utc,
            engine_version=engine_version,
            config_version=config_version,
            schema_versions=schema_versions,
            plugin_manifest=plugin_manifest,
        )

    def write_artifact_edge(
        self,
        conn: Any,
        *,
        child_artifact_id: str,
        parent_artifact_id: str,
        relation: str,
    ) -> None:
        _write_artifact_edge(
            conn,
            child_artifact_id=child_artifact_id,
            parent_artifact_id=parent_artifact_id,
            relation=relation,
        )

    def query_analytics(
        self,
        query: str,
        *,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        return None
