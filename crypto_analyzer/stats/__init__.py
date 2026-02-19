"""Stats corrections: Reality Check, Romano–Wolf stub. Phase 3 Slice 4."""

from __future__ import annotations

from .reality_check import (
    RealityCheckConfig,
    make_null_generator_stationary,
    reality_check_pvalue,
    run_reality_check,
)

__all__ = [
    "RealityCheckConfig",
    "reality_check_pvalue",
    "run_reality_check",
    "make_null_generator_stationary",
]
