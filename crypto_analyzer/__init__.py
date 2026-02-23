"""
Top-level public API surface. Stable facades only.
Canonical entrypoint: import crypto_analyzer; use crypto_analyzer.core, crypto_analyzer.data, etc.
Does not import cli. rng is a namespace re-export (shim to core.seeding).
"""

from __future__ import annotations

from . import artifacts, core, data, governance, pipeline, rng, stats
from ._version import __version__

# Do not add exports without updating __all__.
__all__ = [
    "__version__",
    "artifacts",
    "core",
    "data",
    "governance",
    "pipeline",
    "rng",
    "stats",
]
