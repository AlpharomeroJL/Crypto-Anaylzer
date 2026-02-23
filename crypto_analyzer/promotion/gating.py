"""
Promotion gating: deterministic evaluate_candidate(bundle, thresholds, regime_summary_df).
Interfaces only; no UI or automatic promotion wiring. Phase 3 Slice 2.
See docs/spec/phase3_regimes_slice2_alignment.md and components/testing_acceptance.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass
class EligibilityReport:
    """Phase 1: Result of evaluate_eligibility; must be persisted for candidate/accepted promotion."""

    passed: bool
    level: Literal["exploratory", "candidate", "accepted"]
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Evidence snapshot for persistence (run_key, run_instance_id, dataset_id_v2, engine_version, config_version)
    run_key: str = ""
    run_instance_id: str = ""
    dataset_id_v2: str = ""
    engine_version: str = ""
    config_version: str = ""


def evaluate_eligibility(
    bundle: ValidationBundle,
    level: Literal["exploratory", "candidate", "accepted"],
    rc_summary: Optional[dict] = None,
) -> EligibilityReport:
    """
    Phase 1 gatekeeper: eligibility for promotion level. Separate from PromotionDecision.
    Exploratory: warn-only. Candidate/Accepted: fail-closed (STRICT dataset, run_key, version pins, RW when enabled).
    rc_summary: optional RC/RW result dict; used for rw_enabled/rw_adjusted_p_values when not in bundle.meta.
    """
    meta = getattr(bundle, "meta", None) or {}
    if rc_summary is None:
        rc_summary = {}
    run_id = getattr(bundle, "run_id", "") or meta.get("run_id", "")
    blockers: list[str] = []
    warnings: list[str] = []

    dataset_id_v2 = meta.get("dataset_id_v2") or getattr(bundle, "dataset_id_v2", None)
    dataset_hash_algo = meta.get("dataset_hash_algo") or getattr(bundle, "dataset_hash_algo", None)
    dataset_hash_mode = meta.get("dataset_hash_mode") or getattr(bundle, "dataset_hash_mode", None)
    run_key = meta.get("run_key") or getattr(bundle, "run_key", None)
    engine_version = meta.get("engine_version") or getattr(bundle, "engine_version", None)
    config_version = meta.get("config_version") or getattr(bundle, "config_version", None)
    research_spec_version = meta.get("research_spec_version") or getattr(bundle, "research_spec_version", None)

    if level == "exploratory":
        if not dataset_id_v2:
            warnings.append("dataset_id_v2 missing (required for candidate/accepted)")
        if not run_key:
            warnings.append("run_key missing (required for candidate/accepted)")
        try:
            from crypto_analyzer.contracts.validation_bundle_contract import validate_bundle_for_level

            _ok, _reasons, contract_warnings = validate_bundle_for_level(meta, level)
            warnings.extend(contract_warnings)
        except Exception:
            pass
        return EligibilityReport(
            passed=True,
            level=level,
            blockers=[],
            warnings=warnings,
            run_key=run_key or "",
            run_instance_id=run_id,
            dataset_id_v2=dataset_id_v2 or "",
            engine_version=engine_version or "",
            config_version=config_version or "",
        )

    # Candidate/Accepted: fail-closed
    # Fold-causality: when walk-forward was used, require valid attestation (Phase 2B)
    walk_forward_used = meta.get("walk_forward_used") or meta.get("fold_causality_attestation_path")
    if walk_forward_used and level in ("candidate", "accepted"):
        from crypto_analyzer.fold_causality.attestation import (
            FOLD_CAUSALITY_ATTESTATION_SCHEMA_VERSION,
            validate_attestation,
        )

        att_ver = meta.get("fold_causality_attestation_schema_version")
        if att_ver != FOLD_CAUSALITY_ATTESTATION_SCHEMA_VERSION:
            blockers.append(
                f"fold_causality_attestation_schema_version must be {FOLD_CAUSALITY_ATTESTATION_SCHEMA_VERSION} (got {att_ver!r})"
            )
        att = meta.get("fold_causality_attestation")
        if not isinstance(att, dict):
            blockers.append("fold_causality_attestation missing or not a dict (required when walk-forward used)")
        else:
            att_ok, att_blockers = validate_attestation(att)
            if not att_ok:
                blockers.extend(att_blockers)

    # RC summary schema version required when rc_summary is used (non-empty)
    if rc_summary and level in ("candidate", "accepted"):
        from crypto_analyzer.contracts.schema_versions import RC_SUMMARY_SCHEMA_VERSION

        rc_ver = rc_summary.get("rc_summary_schema_version")
        if rc_ver != RC_SUMMARY_SCHEMA_VERSION:
            blockers.append(f"rc_summary_schema_version must be {RC_SUMMARY_SCHEMA_VERSION} (got {rc_ver!r})")

    if not (dataset_id_v2 and str(dataset_id_v2).strip()):
        blockers.append("dataset_id_v2 missing")
    if dataset_hash_algo != "sqlite_logical_v2":
        blockers.append(f"dataset_hash_algo must be sqlite_logical_v2 (got {dataset_hash_algo!r})")
    if dataset_hash_mode != "STRICT":
        blockers.append(f"dataset_hash_mode must be STRICT for promotion (got {dataset_hash_mode!r})")
    if not (run_key and str(run_key).strip()):
        blockers.append("run_key missing")
    if not (engine_version and str(engine_version).strip()):
        blockers.append("engine_version missing")
    if not (config_version is not None):
        blockers.append("config_version missing")
    if research_spec_version is None and level == "accepted":
        warnings.append("research_spec_version recommended for accepted")

    # RW: when rw_enabled, require rw_adjusted_p_values present and valid (gatekeeper contract)
    rw_enabled = meta.get("rw_enabled") or rc_summary.get("rw_enabled", False)
    rw_skipped = meta.get("rw_skipped_reason") or rc_summary.get("rw_skipped_reason")
    rw_adj = meta.get("rw_adjusted_p_values")
    if rw_adj is None and isinstance(rc_summary.get("rw_adjusted_p_values"), (dict, pd.Series)):
        rw_adj = rc_summary["rw_adjusted_p_values"]
    if isinstance(rw_adj, pd.Series):
        rw_adj = rw_adj.to_dict()
    hypothesis_ids = rc_summary.get("hypothesis_ids") if isinstance(rc_summary.get("hypothesis_ids"), list) else None
    actual_n_sim = rc_summary.get("actual_n_sim")
    if actual_n_sim is not None and isinstance(actual_n_sim, (int, float)):
        actual_n_sim = int(actual_n_sim)
    requested_n_sim = rc_summary.get("requested_n_sim")
    if requested_n_sim is not None and isinstance(requested_n_sim, (int, float)):
        requested_n_sim = int(requested_n_sim)
    # Optional polish: for candidate/accepted, do not tolerate large null shortfall (regression guard)
    if (
        level in ("candidate", "accepted")
        and requested_n_sim is not None
        and requested_n_sim > 0
        and actual_n_sim is not None
    ):
        if actual_n_sim < requested_n_sim * 0.95:
            blockers.append(
                f"actual_n_sim ({actual_n_sim}) < 95% of requested_n_sim ({requested_n_sim}); promotion requires sufficient null simulations"
            )
    if rw_enabled:
        if rw_skipped:
            blockers.append(f"RW skipped: {rw_skipped}")
        elif actual_n_sim is not None and actual_n_sim == 0:
            blockers.append("rw_enabled=True but no null simulations produced (actual_n_sim=0)")
        elif rw_adj is None:
            blockers.append("rw_enabled=True but rw_adjusted_p_values missing")
        elif isinstance(rw_adj, dict):
            if hypothesis_ids is not None and len(rw_adj) != len(hypothesis_ids):
                blockers.append(
                    f"rw_adjusted_p_values length ({len(rw_adj)}) must match hypothesis count ({len(hypothesis_ids)})"
                )
            else:
                # Index alignment: keys must match hypothesis_ids (set + exact order for downstream merge safety)
                if hypothesis_ids is not None:
                    rw_keys_list = list(rw_adj.keys())
                    if set(rw_keys_list) != set(hypothesis_ids):
                        blockers.append("rw_adjusted_p_values keys must match hypothesis_ids")
                    elif rw_keys_list != hypothesis_ids:
                        blockers.append("rw_adjusted_p_values key order must match hypothesis_ids")
                    else:
                        for k, v in rw_adj.items():
                            if v is None or (isinstance(v, float) and (v < 0 or v > 1 or v != v)):
                                blockers.append("rw_adjusted_p_values must be in [0,1] and finite")
                                break
                else:
                    for k, v in rw_adj.items():
                        if v is None or (isinstance(v, float) and (v < 0 or v > 1 or v != v)):
                            blockers.append("rw_adjusted_p_values must be in [0,1] and finite")
                            break

    # Bundle contract validator (additive): candidate/accepted fail if schema/provenance missing
    try:
        from crypto_analyzer.contracts.validation_bundle_contract import validate_bundle_for_level

        contract_ok, contract_reasons, contract_warnings = validate_bundle_for_level(meta, level)
        if not contract_ok:
            blockers.extend(contract_reasons)
        warnings.extend(contract_warnings)
    except Exception:
        pass

    passed = len(blockers) == 0
    return EligibilityReport(
        passed=passed,
        level=level,
        blockers=blockers,
        warnings=warnings,
        run_key=run_key or "",
        run_instance_id=run_id,
        dataset_id_v2=dataset_id_v2 or "",
        engine_version=engine_version or "",
        config_version=config_version or "",
    )


def evaluate_candidate(
    bundle: ValidationBundle,
    thresholds: ThresholdConfig,
    regime_summary_df: Optional[pd.DataFrame] = None,
    rc_summary: Optional[dict] = None,
    execution_evidence: Optional["ExecutionEvidence"] = None,
    target_status: str = "exploratory",
    allow_missing_execution_evidence: bool = False,
    execution_evidence_base_path: Optional[str] = None,
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
            missing = execution_evidence.validate_required(base_path=execution_evidence_base_path)
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
