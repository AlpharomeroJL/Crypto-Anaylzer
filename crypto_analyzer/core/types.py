"""
Shared dataclasses and types for crypto_analyzer. No business logic.
RunContext and ExecContext live in core.context; extend here when multiple packages
need additional shared types. Intentionally minimal; populated when shared types emerge.
"""

from __future__ import annotations

__all__: list[str] = []
