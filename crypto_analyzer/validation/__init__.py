"""Validation helpers: regime-conditioned IC/decay/coverage. Phase 3 Slice 2."""

from __future__ import annotations

from .regime_conditioning import (
    attach_regime_label,
    ic_decay_by_regime,
    ic_summary_by_regime,
    ic_summary_by_regime_multi,
    regime_coverage,
)

__all__ = [
    "attach_regime_label",
    "ic_summary_by_regime",
    "ic_summary_by_regime_multi",
    "ic_decay_by_regime",
    "regime_coverage",
]
