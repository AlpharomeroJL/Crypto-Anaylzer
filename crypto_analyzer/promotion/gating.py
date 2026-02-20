"""
Promotion gating: deterministic evaluate_candidate(bundle, thresholds, regime_summary_df).
Interfaces only; no UI or automatic promotion wiring. Phase 3 Slice 2.
See docs/spec/phase3_regimes_slice2_alignment.md and components/testing_acceptance.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Optional

import pandas as pd

from crypto_analyzer.validation_bundle import ValidationBundle

if TYPE_CHECKING:
    from .execution_evidence import ExecutionEvidence

# Minimum number of regimes with enough samples when require_regime_robustness is True (documented default)
MIN_REGIMES_WITH_SAMPLES = 2


@dataclass
class ThresholdConfig:
    """Minimum evidence thresholds; require_regime_robustness=False by default. Slice 4: RC opt-in. PR2: execution gates."""

    ic_mean_min: float = 0.02
    tstat_min: float = 2.5
    p_value_max: float = 0.05
    deflated_sharpe_min: Optional[float] = 1.0
    require_regime_robustness: bool = False
    worst_regime_ic_mean_min: Optional[float] = None  # used only when require_regime_robustness=True
    require_reality_check: bool = False
    max_rc_p_value: float = 0.05  # used only when require_reality_check=True
    # Execution realism (PR2): default None to avoid brittleness
    require_execution_evidence: bool = False
    min_liquidity_usd_min: Optional[float] = None
    max_participation_rate_max: Optional[float] = None


@dataclass
class PromotionDecision:
    """Result of evaluate_candidate: status, reasons, metrics_snapshot. PR2: warnings (e.g. override) recorded for audit, do not cause reject."""

    status: Literal["exploratory", "candidate", "accepted", "rejected"]
    reasons: list[str] = field(default_factory=list)
    metrics_snapshot: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)  # audit only; do not cause reject


def evaluate_candidate(
    bundle: ValidationBundle,
    thresholds: ThresholdConfig,
    regime_summary_df: Optional[pd.DataFrame] = None,
    rc_summary: Optional[dict] = None,
    execution_evidence: Optional["ExecutionEvidence"] = None,
    target_status: str = "exploratory",
    allow_missing_execution_evidence: bool = False,
    execution_evidence_base_path: Optional[Path] = None,
) -> PromotionDecision:
    """
    Deterministic promotion gate. No randomness.
    If require_regime_robustness: reject if any regime's mean_ic < worst_regime_ic_mean_min
    or if fewer than MIN_REGIMES_WITH_SAMPLES regimes have enough samples.
    PR2: When target_status in {candidate, accepted} or require_execution_evidence=True,
    require execution evidence unless allow_missing_execution_evidence=True (then add WARN and record override).
    Soft thresholds (min_liquidity_usd_min, max_participation_rate_max) applied only when set.
    """
    reasons: list[str] = []
    metrics_snapshot: dict = {}
    warnings: list[str] = []

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

    if thresholds.require_reality_check:
        rc_p = None
        if rc_summary and isinstance(rc_summary.get("rc_p_value"), (int, float)):
            rc_p = float(rc_summary["rc_p_value"])
        elif getattr(bundle, "meta", None) and isinstance(bundle.meta.get("rc_p_value"), (int, float)):
            rc_p = float(bundle.meta["rc_p_value"])
        if rc_p is None:
            reasons.append("require_reality_check=True but no rc_p_value in meta or rc_summary")
        elif rc_p > thresholds.max_rc_p_value:
            reasons.append(f"rc_p_value {rc_p:.4f} > {thresholds.max_rc_p_value}")

    # Execution evidence gate (PR2): when target is candidate/accepted or require_execution_evidence
    enforce_exec = target_status in ("candidate", "accepted") or thresholds.require_execution_evidence
    if enforce_exec:
        if allow_missing_execution_evidence:
            warnings.append("allow_missing_execution_evidence: execution evidence not checked")
        elif execution_evidence is None:
            reasons.append(
                "execution evidence required (target beyond exploratory or require_execution_evidence) but none provided"
            )
        else:
            base = execution_evidence_base_path
            missing = execution_evidence.validate_required(base_path=base)
            if missing:
                reasons.append("execution evidence missing required: " + ", ".join(missing))
            else:
                # Soft thresholds only when explicitly set
                if thresholds.min_liquidity_usd_min is not None and execution_evidence.min_liquidity_usd is not None:
                    if execution_evidence.min_liquidity_usd < thresholds.min_liquidity_usd_min:
                        reasons.append(
                            f"min_liquidity_usd {execution_evidence.min_liquidity_usd} < {thresholds.min_liquidity_usd_min}"
                        )
                if (
                    thresholds.max_participation_rate_max is not None
                    and execution_evidence.max_participation_rate is not None
                ):
                    if execution_evidence.max_participation_rate > thresholds.max_participation_rate_max:
                        reasons.append(
                            f"max_participation_rate {execution_evidence.max_participation_rate} > {thresholds.max_participation_rate_max}"
                        )

    if reasons:
        return PromotionDecision(
            status="rejected", reasons=reasons, metrics_snapshot=metrics_snapshot, warnings=warnings
        )
    return PromotionDecision(status="accepted", reasons=[], metrics_snapshot=metrics_snapshot, warnings=warnings)
