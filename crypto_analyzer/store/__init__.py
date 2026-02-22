"""
Store: SQLite/DuckDB backends, persistence primitives. Phase 3 A5.
No business logic. SQLite authoritative for governance and lineage.
"""

from __future__ import annotations

from .backend import Backend, get_backend, set_backend

__all__ = ["Backend", "get_backend", "set_backend"]
