"""
Core: pure research and validation logic (stats, folds, RNG, contracts, run identity).
Phase 3 A1. Must NOT depend on governance (promotion), store, or CLI.
"""

from __future__ import annotations

from .context import ExecContext, RunContext

__all__ = ["ExecContext", "RunContext"]
