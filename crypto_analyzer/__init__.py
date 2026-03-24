"""
Top-level public API surface. Stable facades only.
Canonical entrypoint: import crypto_analyzer; use crypto_analyzer.core, crypto_analyzer.data, etc.
Does not import cli. rng is a namespace re-export (shim to core.seeding).
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType

from ._version import __version__

_LAZY_FACADES = {
    "artifacts": ".artifacts",
    "core": ".core",
    "data": ".data",
    "governance": ".governance",
    "pipeline": ".pipeline",
    "rng": ".rng",
    "stats": ".stats",
}

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


def __getattr__(name: str) -> ModuleType:
    """Lazily load facade modules so package import stays lightweight."""
    if name in _LAZY_FACADES:
        module = import_module(_LAZY_FACADES[name], __name__)
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Expose lazy facade names to completion and introspection."""
    return sorted(set(globals()) | set(__all__))
