"""
RegimeDetector: fit on train, predict with mode="filter" only in test/validation.

No smoothing on test data (risk_audit). Model: thresholded vol regime (low/med/high)
with hysteresis. See docs/spec/components/interfaces.md and risk_audit.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

# Regime labels for vol-based model
REGIME_LOW_VOL = "low_vol"
REGIME_MED_VOL = "med_vol"
REGIME_HIGH_VOL = "high_vol"


@dataclass
class RegimeConfig:
    """Config for thresholded vol regime with hysteresis."""

    vol_column: str = "realized_vol"
    """Feature column used for regime (default: realized_vol)."""
    low_pct: float = 33.33
    """Percentile below which vol is low_vol."""
    high_pct: float = 66.67
    """Percentile above which vol is high_vol."""
    hysteresis_pct: float = 5.0
    """Extra margin to avoid flipping: switch up only when vol > high_pct + hysteresis."""
    allow_smooth_in_test: bool = False
    """If False, predict(..., mode='smooth') raises in validation context."""


@dataclass
class RegimeModel:
    """Fitted thresholds and state for filter-only prediction."""

    low_threshold: float
    high_threshold: float
    hysteresis_low: float
    hysteresis_high: float
    config: RegimeConfig
    fit_timestamps: pd.Index
    """Timestamps used in fit (for leakage check)."""


@dataclass
class RegimeStateSeries:
    """Regime label and probability per timestamp. Probabilities sum to 1.0 ± 1e-6 per row."""

    ts_utc: pd.Series
    regime_label: pd.Series
    regime_prob: pd.Series
    """Probability of the assigned regime_label (for DB/schema)."""
    prob_low: Optional[pd.Series] = None
    prob_med: Optional[pd.Series] = None
    prob_high: Optional[pd.Series] = None
    """Full probability vector when available (prob_low + prob_med + prob_high = 1)."""


def fit_regime_detector(
    train_features: pd.DataFrame,
    config: Optional[RegimeConfig] = None,
) -> RegimeModel:
    """
    Fit regime model on train_features only. Uses vol_column percentiles.

    train_features must have ts_utc and the column named in config.vol_column.
    Deterministic: sort by ts_utc, then compute percentiles.
    """
    cfg = config or RegimeConfig()
    if train_features.empty:
        raise ValueError("train_features must not be empty")
    if cfg.vol_column not in train_features.columns:
        raise ValueError(f"train_features must have column {cfg.vol_column!r}")

    df = train_features.sort_values("ts_utc").reset_index(drop=True)
    vol = df[cfg.vol_column].dropna()
    if vol.empty:
        raise ValueError(f"No non-NaN values in {cfg.vol_column}")

    low_threshold = float(np.nanpercentile(vol.values, cfg.low_pct))
    high_threshold = float(np.nanpercentile(vol.values, cfg.high_pct))
    half_hyst = (
        (high_threshold - low_threshold) * (cfg.hysteresis_pct / 100.0) if high_threshold > low_threshold else 0.0
    )
    hysteresis_low = low_threshold - half_hyst
    hysteresis_high = high_threshold + half_hyst

    return RegimeModel(
        low_threshold=low_threshold,
        high_threshold=high_threshold,
        hysteresis_low=hysteresis_low,
        hysteresis_high=hysteresis_high,
        config=cfg,
        fit_timestamps=df["ts_utc"].index if "ts_utc" in df.columns else df.index,
    )


def predict_regime(
    test_features: pd.DataFrame,
    model: RegimeModel,
    mode: str = "filter",
    allow_smooth: bool = False,
) -> RegimeStateSeries:
    """
    Predict regime labels (and probabilities) on test_features using filter-only logic.

    mode must be "filter" for test/validation. If mode="smooth" and allow_smooth is False,
    raises ValueError (no smoothing in test per risk_audit).
    Process is causal: at each row t we use only data up to and including t.
    """
    if mode not in ("filter", "smooth"):
        raise ValueError(f"mode must be 'filter' or 'smooth', got {mode!r}")
    if mode == "smooth" and not (allow_smooth or model.config.allow_smooth_in_test):
        raise ValueError(
            "mode='smooth' is not allowed in test/validation (leakage risk). "
            "Use mode='filter' only. See docs/spec/components/risk_audit.md."
        )

    cfg = model.config
    if test_features.empty:
        return RegimeStateSeries(
            ts_utc=pd.Series(dtype=object),
            regime_label=pd.Series(dtype=object),
            regime_prob=pd.Series(dtype=float),
        )
    if cfg.vol_column not in test_features.columns:
        raise ValueError(f"test_features must have column {cfg.vol_column!r}")

    df = test_features.sort_values("ts_utc").reset_index(drop=True)
    vol = df[cfg.vol_column].astype(float)

    # Filter-only: sequential assignment with hysteresis (no future data)
    labels = []
    plow, pmed, phigh = [], [], []
    current_regime = REGIME_MED_VOL
    for i in range(len(df)):
        v = vol.iloc[i]
        if np.isnan(v):
            labels.append(current_regime)
            plow.append(np.nan)
            pmed.append(np.nan)
            phigh.append(np.nan)
            continue
        if v <= model.hysteresis_low:
            current_regime = REGIME_LOW_VOL
            p_l = 1.0 - (v / model.hysteresis_low) if model.hysteresis_low > 0 else 1.0
            p_l = max(0.0, min(1.0, p_l))
            p_m = (1.0 - p_l) * 0.5
            p_h = (1.0 - p_l) * 0.5
            plow.append(p_l)
            pmed.append(p_m)
            phigh.append(p_h)
        elif v >= model.hysteresis_high:
            current_regime = REGIME_HIGH_VOL
            p_h = min(1.0, (v - model.hysteresis_high) / max(1e-12, v - model.hysteresis_high + 0.01))
            p_h = max(0.0, min(1.0, p_h))
            p_l = (1.0 - p_h) * 0.5
            p_m = (1.0 - p_h) * 0.5
            plow.append(p_l)
            pmed.append(p_m)
            phigh.append(p_h)
        else:
            current_regime = REGIME_MED_VOL
            p_m = 0.6
            p_l = 0.2
            p_h = 0.2
            plow.append(p_l)
            pmed.append(p_m)
            phigh.append(p_h)
        labels.append(current_regime)

    # Normalize so sum = 1.0 per row
    plow = np.array(plow)
    pmed = np.array(pmed)
    phigh = np.array(phigh)
    s = plow + pmed + phigh
    ok = np.isfinite(s) & (s > 0)
    plow = np.where(ok, plow / s, np.nan)
    pmed = np.where(ok, pmed / s, np.nan)
    phigh = np.where(ok, phigh / s, np.nan)

    regime_label_series = pd.Series(labels, index=df.index)
    prob_of_label = []
    for i, lab in enumerate(labels):
        if lab == REGIME_LOW_VOL:
            prob_of_label.append(plow[i])
        elif lab == REGIME_HIGH_VOL:
            prob_of_label.append(phigh[i])
        else:
            prob_of_label.append(pmed[i])
    regime_prob_series = pd.Series(prob_of_label, index=df.index)
    ts_utc = df["ts_utc"] if "ts_utc" in df.columns else pd.Series(df.index, index=df.index)

    return RegimeStateSeries(
        ts_utc=ts_utc,
        regime_label=regime_label_series,
        regime_prob=regime_prob_series,
        prob_low=pd.Series(plow, index=df.index),
        prob_med=pd.Series(pmed, index=df.index),
        prob_high=pd.Series(phigh, index=df.index),
    )
