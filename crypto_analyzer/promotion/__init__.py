"""Promotion gating: evaluate_candidate, ThresholdConfig, PromotionDecision. Phase 3 Slice 2."""

from __future__ import annotations

from .gating import (
    EligibilityReport,
    PromotionDecision,
    ThresholdConfig,
    evaluate_candidate,
    evaluate_eligibility,
)

__all__ = [
    "EligibilityReport",
    "PromotionDecision",
    "ThresholdConfig",
    "evaluate_candidate",
    "evaluate_eligibility",
]
