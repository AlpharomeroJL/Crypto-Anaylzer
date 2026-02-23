"""
Shared typing aliases and Protocols for crypto_analyzer.
Stable surface; no runtime behavior. Extend with new Protocols/TypeAlias only.
"""

from __future__ import annotations

from typing import Protocol, TypeVar

# Placeholder for future shared type aliases (e.g. PathLike, RunKey).
# No behavior change; add Protocols here when needed.
T = TypeVar("T")


class SupportsRunKey(Protocol):
    """Protocol for objects that expose a run_key (e.g. RunContext)."""

    run_key: str


__all__ = ["SupportsRunKey", "T"]
