"""
Phase 3 regime models: causal features, RegimeDetector (fit/predict filter-only),
and materialization to regime_runs / regime_states.

Gated by CRYPTO_ANALYZER_ENABLE_REGIMES=1. See docs/spec/components/interfaces.md
and docs/spec/components/risk_audit.md (filter-only, no smoothing in test).
"""

from __future__ import annotations

from ._flags import is_regimes_enabled
from .legacy import (
    REGIME_CHOP,
    REGIME_DISPERSION,
    REGIME_MACRO_BETA,
    REGIME_RISK_OFF,
    classify_market_regime,
    explain_regime,
)
from .regime_detector import RegimeConfig, RegimeModel, RegimeStateSeries, fit_regime_detector, predict_regime
from .regime_features import RegimeFeatureConfig, build_regime_features
from .regime_materialize import RegimeMaterializeConfig, materialize_regime_run

__all__ = [
    "is_regimes_enabled",
    "classify_market_regime",
    "explain_regime",
    "REGIME_CHOP",
    "REGIME_DISPERSION",
    "REGIME_MACRO_BETA",
    "REGIME_RISK_OFF",
    "RegimeConfig",
    "RegimeModel",
    "RegimeStateSeries",
    "fit_regime_detector",
    "predict_regime",
    "RegimeFeatureConfig",
    "build_regime_features",
    "RegimeMaterializeConfig",
    "materialize_regime_run",
]
