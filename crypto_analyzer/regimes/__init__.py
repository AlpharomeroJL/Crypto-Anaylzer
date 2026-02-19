"""
Phase 3 regime models: causal features, RegimeDetector (fit/predict filter-only),
and materialization to regime_runs / regime_states.

Gated by CRYPTO_ANALYZER_ENABLE_REGIMES=1. See docs/spec/components/interfaces.md
and docs/spec/components/risk_audit.md (filter-only, no smoothing in test).
"""

from __future__ import annotations

import os


def is_regimes_enabled() -> bool:
    """
    True iff CRYPTO_ANALYZER_ENABLE_REGIMES is set to a truthy value (1, true, yes).

    Read at call time so modules remain importable with flag OFF.
    """
    v = os.environ.get("CRYPTO_ANALYZER_ENABLE_REGIMES", "0").strip().lower()
    return v in ("1", "true", "yes")


from .regime_detector import RegimeConfig, RegimeModel, RegimeStateSeries, fit_regime_detector, predict_regime
from .regime_features import RegimeFeatureConfig, build_regime_features
from .regime_materialize import materialize_regime_run

__all__ = [
    "is_regimes_enabled",
    "RegimeConfig",
    "RegimeModel",
    "RegimeStateSeries",
    "fit_regime_detector",
    "predict_regime",
    "RegimeFeatureConfig",
    "build_regime_features",
    "materialize_regime_run",
]
