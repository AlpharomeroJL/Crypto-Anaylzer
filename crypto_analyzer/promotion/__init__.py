"""Promotion gating: evaluate_candidate, ThresholdConfig, PromotionDecision. Phase 3 Slice 2."""

from __future__ import annotations

from .gating import PromotionDecision, ThresholdConfig, evaluate_candidate

__all__ = ["ThresholdConfig", "PromotionDecision", "evaluate_candidate"]
