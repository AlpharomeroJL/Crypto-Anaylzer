"""
Stable facade: core run/execution context only. No governance, store, cli, or promotion.
Phase 3 A1. Imports are minimal (context only). Do not add exports without updating __all__.
"""

from __future__ import annotations

from .context import ExecContext, RunContext

# Do not add exports without updating __all__.
__all__ = ["ExecContext", "RunContext"]
