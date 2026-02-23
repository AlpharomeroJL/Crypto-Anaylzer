"""
Stable facade: stats entrypoints (Reality Check, Romano–Wolf stub). Phase 3 Slice 4.
Re-exports from .reality_check only. Does not import cli or promotion. Do not add exports without updating __all__.
"""

from __future__ import annotations

from .reality_check import (
    RealityCheckConfig,
    make_null_generator_stationary,
    reality_check_pvalue,
    run_reality_check,
)

# Do not add exports without updating __all__.
__all__ = [
    "RealityCheckConfig",
    "reality_check_pvalue",
    "run_reality_check",
    "make_null_generator_stationary",
]
