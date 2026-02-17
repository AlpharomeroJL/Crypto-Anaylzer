"""
Market regime: combine dispersion_z, vol_regime, beta_state into a single label.
Research-only; no execution.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

# Regime labels
REGIME_MACRO_BETA = "macro_beta"
REGIME_DISPERSION = "dispersion"
REGIME_RISK_OFF = "risk_off"
REGIME_CHOP = "chop"


def classify_market_regime(
    dispersion_z: Optional[float],
    vol_regime: Optional[str],
    beta_state: Optional[str],
) -> str:
    """
    Deterministic mapping from dispersion_z, vol_regime, beta_state to a single regime.

    Rules (evaluated in order):
    - risk_off: vol_regime == "rising" and (beta_state == "compressed" or dispersion_z < -1)
    - macro_beta: dispersion_z is not NaN and dispersion_z < -1  (low dispersion => market-driven)
    - dispersion: dispersion_z is not NaN and dispersion_z > 1   (high dispersion => relative value)
    - chop: vol_regime == "stable" and beta_state == "stable"
    - default: macro_beta if dispersion_z <= 0 else dispersion; fallback chop
    """
    dz = dispersion_z if dispersion_z is not None and not np.isnan(dispersion_z) else None
    vol = (vol_regime or "").strip().lower()
    beta = (beta_state or "").strip().lower()

    # Risk-off: rising vol and (compressed beta or very low dispersion)
    if vol == "rising" and (beta == "compressed" or (dz is not None and dz < -1)):
        return REGIME_RISK_OFF

    # Low dispersion => macro beta
    if dz is not None and dz < -1:
        return REGIME_MACRO_BETA

    # High dispersion => dispersion (relative value)
    if dz is not None and dz > 1:
        return REGIME_DISPERSION

    # Chop: stable vol and stable beta
    if vol == "stable" and beta == "stable":
        return REGIME_CHOP

    # Default by dispersion
    if dz is not None:
        return REGIME_MACRO_BETA if dz <= 0 else REGIME_DISPERSION
    return REGIME_CHOP


def explain_regime(regime: str) -> str:
    """One to two line interpretation of the regime label."""
    if regime == REGIME_MACRO_BETA:
        return "Low cross-asset dispersion; returns driven by market factor (beta/trend)."
    if regime == REGIME_DISPERSION:
        return "High cross-asset dispersion; relative value / pair trades more relevant."
    if regime == REGIME_RISK_OFF:
        return "Vol rising with compressed beta or low dispersion; defensive regime."
    if regime == REGIME_CHOP:
        return "Stable vol and beta; range-bound, mean-reversion conditions."
    return "Unclassified or unknown inputs."
