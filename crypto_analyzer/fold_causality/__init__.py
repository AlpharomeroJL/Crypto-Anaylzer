"""
Phase 2B: Fold-causality architecture.
Strict train/test separation, purge/embargo, transform contracts, attestation for promotion.
"""

from __future__ import annotations

from .attestation import (
    FOLD_CAUSALITY_ATTESTATION_SCHEMA_VERSION,
    build_fold_causality_attestation,
)
from .folds import FoldSpec, SplitPlan, make_walk_forward_splits
from .transforms import (
    TRANSFORM_REGISTRY,
    ExogenousTransform,
    TrainableTransform,
    TransformSpec,
)

__all__ = [
    "FoldSpec",
    "SplitPlan",
    "make_walk_forward_splits",
    "ExogenousTransform",
    "TrainableTransform",
    "TransformSpec",
    "TRANSFORM_REGISTRY",
    "FOLD_CAUSALITY_ATTESTATION_SCHEMA_VERSION",
    "build_fold_causality_attestation",
]
