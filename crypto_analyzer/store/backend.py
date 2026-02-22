"""
Backend interface: read_table, write_artifact_lineage (SQLite), query_analytics (DuckDB optional).
Phase 3 A5. SQLite remains authoritative for governance and lineage.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Default backend instance (set by get_backend)
_backend: Optional["Backend"] = None


class Backend(ABC):
    """
    Read/compute backend. Lineage and governance always write to SQLite.
    """

    @abstractmethod
    def read_table(
        self,
        table: str,
        *,
        db_path: Optional[Union[str, Path]] = None,
        columns: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> Any:
        """Read table as DataFrame (or equivalent). db_path required for SQLite."""
        ...

    @abstractmethod
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
        """Write one row to artifact_lineage (SQLite). conn is sqlite3.Connection."""
        ...

    @abstractmethod
    def write_artifact_edge(
        self,
        conn: Any,
        *,
        child_artifact_id: str,
        parent_artifact_id: str,
        relation: str,
    ) -> None:
        """Write one row to artifact_edges (SQLite)."""
        ...

    def query_analytics(
        self,
        query: str,
        *,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Optional: run analytics query (e.g. DuckDB). Default returns None (not implemented).
        """
        return None


def get_backend() -> Backend:
    """Return the current backend. Defaults to SQLite backend if not set."""
    global _backend
    if _backend is None:
        from .sqlite_backend import SQLiteBackend

        _backend = SQLiteBackend()
    return _backend


def set_backend(backend: Backend) -> None:
    """Set the global backend (e.g. DuckDB for analytics)."""
    global _backend
    _backend = backend
