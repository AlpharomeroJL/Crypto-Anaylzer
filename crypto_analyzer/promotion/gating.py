"""
Promotion gating: deterministic evaluate_candidate(bundle, thresholds, regime_summary_df).
Interfaces only; no UI or automatic promotion wiring. Phase 3 Slice 2.
See docs/spec/phase3_regimes_slice2_alignment.md and components/testing_acceptance.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

import pandas as pd

from crypto_analyzer.validation_bundle import ValidationBundle

# Minimum number of regimes with enough samples when require_regime_robustness is True (documented default)
MIN_REGIMES_WITH_SAMPLES = 2


@dataclass
class ThresholdConfig:
    """Minimum evidence thresholds; require_regime_robustness=False by default."""

    ic_mean_min: float = 0.02
    tstat_min: float = 2.5
    p_value_max: float = 0.05
    deflated_sharpe_min: Optional[float] = 1.0
    require_regime_robustness: bool = False
    worst_regime_ic_mean_min: Optional[float] = None  # used only when require_regime_robustness=True


@dataclass
class PromotionDecision:
    """Result of evaluate_candidate: status, reasons, metrics_snapshot."""

    status: Literal["exploratory", "candidate", "accepted", "rejected"]
    reasons: list[str] = field(default_factory=list)
    metrics_snapshot: dict = field(default_factory=dict)


def evaluate_candidate(
    bundle: ValidationBundle,
    thresholds: ThresholdConfig,
    regime_summary_df: Optional[pd.DataFrame] = None,
) -> PromotionDecision:
    """
    Deterministic promotion gate. No randomness.
    If require_regime_robustness: reject if any regime's mean_ic < worst_regime_ic_mean_min
    or if fewer than MIN_REGIMES_WITH_SAMPLES regimes have enough samples.
    Otherwise ignore regime robustness.
    """
    reasons: list[str] = []
    metrics_snapshot: dict = {}

    # Snapshot from bundle (primary horizon or first)
    horizons = getattr(bundle, "horizons", []) or []
    h = horizons[0] if horizons else None
    ic_summary = getattr(bundle, "ic_summary_by_horizon", {}) or {}
    summary_h = ic_summary.get(h, {}) if h is not None else {}
    mean_ic = summary_h.get("mean_ic")
    t_stat = summary_h.get("t_stat")
    n_obs = summary_h.get("n_obs", 0)
    metrics_snapshot["mean_ic"] = mean_ic
    metrics_snapshot["t_stat"] = t_stat
    metrics_snapshot["n_obs"] = n_obs

    # Base checks (no regime)
    if mean_ic is None:
        return PromotionDecision(
            status="exploratory", reasons=["missing IC summary"], metrics_snapshot=metrics_snapshot
        )
    if mean_ic < thresholds.ic_mean_min:
        reasons.append(f"mean_ic {mean_ic:.4f} < {thresholds.ic_mean_min}")
    if t_stat is not None and thresholds.tstat_min is not None and t_stat < thresholds.tstat_min:
        reasons.append(f"t_stat {t_stat:.4f} < {thresholds.tstat_min}")
    # p_value and deflated_sharpe: if present in meta/snapshot we could check; optional for Slice 2
    if thresholds.require_regime_robustness:
        min_ic_regime = thresholds.worst_regime_ic_mean_min
        if min_ic_regime is None:
            reasons.append("require_regime_robustness=True but worst_regime_ic_mean_min not set")
        elif regime_summary_df is None or regime_summary_df.empty:
            reasons.append("require_regime_robustness=True but no regime summary provided")
        else:
            # regime_summary_df: expect columns regime, mean_ic (and optionally n_bars)
            if "mean_ic" not in regime_summary_df.columns:
                reasons.append("regime summary missing mean_ic column")
            else:
                # Exclude "unknown" if present
                reg_df = regime_summary_df[
                    regime_summary_df.get("regime", pd.Series(dtype=object)).astype(str) != "unknown"
                ]
                n_regimes = len(reg_df)
                if n_regimes < MIN_REGIMES_WITH_SAMPLES:
                    reasons.append(f"fewer than {MIN_REGIMES_WITH_SAMPLES} regimes with samples (got {n_regimes})")
                else:
                    worst = reg_df["mean_ic"].min()
                    if worst < min_ic_regime:
                        reasons.append(f"worst regime mean_ic {worst:.4f} < {min_ic_regime}")

    if reasons:
        return PromotionDecision(status="rejected", reasons=reasons, metrics_snapshot=metrics_snapshot)
    return PromotionDecision(status="accepted", reasons=[], metrics_snapshot=metrics_snapshot)
