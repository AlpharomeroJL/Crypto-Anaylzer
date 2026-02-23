"""
Promotion service: evaluate_and_record using gating and store.
Phase 3 Slice 5. No UI dependencies.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional, Union

import pandas as pd

from crypto_analyzer.timeutils import now_utc_iso
from crypto_analyzer.validation_bundle import ValidationBundle

from .evidence_resolver import resolve_evidence
from .gating import (
    PromotionDecision,
    ThresholdConfig,
    evaluate_candidate,
    evaluate_eligibility,
)
from .store_sqlite import (
    get_candidate,
    insert_eligibility_report,
    promote_to_accepted,
    promote_to_candidate,
    record_event,
    update_status,
)


def _thresholds_snapshot(
    t: ThresholdConfig,
    allow_missing_execution_evidence: bool = False,
) -> Dict[str, Any]:
    """Snapshot of threshold config for event payload (reproducibility). PR2: execution fields + override."""
    out: Dict[str, Any] = {
        "require_reality_check": t.require_reality_check,
        "max_rc_p_value": t.max_rc_p_value,
        "ic_mean_min": t.ic_mean_min,
        "tstat_min": t.tstat_min,
        "p_value_max": t.p_value_max,
        "require_regime_robustness": t.require_regime_robustness,
        "worst_regime_ic_mean_min": t.worst_regime_ic_mean_min,
        "require_execution_evidence": t.require_execution_evidence,
        "min_liquidity_usd_min": t.min_liquidity_usd_min,
        "max_participation_rate_max": t.max_participation_rate_max,
        "allow_missing_execution_evidence": allow_missing_execution_evidence,
    }
    return out


def _artifact_pointers(
    bundle_or_path: Union[ValidationBundle, str, Path],
    evidence: Dict[str, Any],
) -> Dict[str, Any]:
    """Pointers to artifacts consumed (bundle path, rc summary path, regime paths, execution_evidence_path)."""
    out: Dict[str, Any] = {}
    if isinstance(bundle_or_path, (str, Path)):
        out["bundle_path"] = str(bundle_or_path)
    elif evidence.get("bundle_path"):
        out["bundle_path"] = evidence["bundle_path"]
    elif evidence.get("validation_bundle_path"):
        out["bundle_path"] = evidence["validation_bundle_path"]
    for key in (
        "rc_summary_path",
        "ic_summary_by_regime_path",
        "ic_decay_by_regime_path",
        "regime_coverage_path",
        "execution_evidence_path",
    ):
        if evidence.get(key):
            out[key] = evidence[key]
    return out


def evaluate_and_record(
    conn: sqlite3.Connection,
    candidate_id: str,
    thresholds: ThresholdConfig,
    bundle_or_path: Union[ValidationBundle, str, Path],
    *,
    regime_summary_df: Optional[pd.DataFrame] = None,
    rc_summary: Optional[Dict[str, Any]] = None,
    evidence_base_path: Optional[Union[str, Path]] = None,
    target_status: str = "exploratory",
    allow_missing_execution_evidence: bool = False,
) -> PromotionDecision:
    """
    Load candidate; resolve bundle (from instance or path); run gating.evaluate_candidate;
    update candidate status to decision.status; record evaluated event with reasons and snapshot.
    If regime_summary_df or rc_summary not provided but evidence_json has paths, load from
    evidence_base_path (directory for relative paths).
    PR2: Load execution evidence from evidence_json.execution_evidence_path; pass target_status and
    allow_missing_execution_evidence to evaluate_candidate; include in event payload.
    """
    row = get_candidate(conn, candidate_id)
    if row is None:
        return PromotionDecision(
            status="rejected",
            reasons=[f"candidate_id not found: {candidate_id}"],
            metrics_snapshot={},
        )

    evidence: Dict[str, Any] = {}
    if row.get("evidence_json"):
        try:
            evidence = json.loads(row["evidence_json"])
        except Exception:
            pass
    base = Path(evidence_base_path) if evidence_base_path else Path(".")

    bundle_resolved, regime_resolved, rc_resolved, execution_evidence_loaded = resolve_evidence(
        evidence, base, bundle_or_path
    )
    if bundle_resolved is None:
        return PromotionDecision(
            status="rejected",
            reasons=["could not load ValidationBundle from path"],
            metrics_snapshot={},
        )
    bundle = bundle_resolved
    if regime_summary_df is None:
        regime_summary_df = regime_resolved
    if rc_summary is None:
        rc_summary = rc_resolved

    # Sweep-originated candidates: require RC for Candidate/Accepted by default (data-snooping policy).
    # If family_id is set and caller did not set require_reality_check=True, enforce it for this evaluation.
    effective_thresholds = thresholds
    family_id = (row.get("family_id") or "").strip()
    if family_id and not thresholds.require_reality_check:
        effective_thresholds = ThresholdConfig(
            ic_mean_min=thresholds.ic_mean_min,
            tstat_min=thresholds.tstat_min,
            p_value_max=thresholds.p_value_max,
            deflated_sharpe_min=thresholds.deflated_sharpe_min,
            require_regime_robustness=thresholds.require_regime_robustness,
            worst_regime_ic_mean_min=thresholds.worst_regime_ic_mean_min,
            require_reality_check=True,
            max_rc_p_value=thresholds.max_rc_p_value,
            require_execution_evidence=thresholds.require_execution_evidence,
            min_liquidity_usd_min=thresholds.min_liquidity_usd_min,
            max_participation_rate_max=thresholds.max_participation_rate_max,
        )

    decision = evaluate_candidate(
        bundle,
        effective_thresholds,
        regime_summary_df=regime_summary_df,
        rc_summary=rc_summary,
        execution_evidence=execution_evidence_loaded,
        target_status=target_status,
        allow_missing_execution_evidence=allow_missing_execution_evidence,
        execution_evidence_base_path=str(base) if base else None,
    )

    # Snapshot inputs for "why was this accepted?" reproducibility
    evidence = {}
    if row.get("evidence_json"):
        try:
            evidence = json.loads(row["evidence_json"])
        except Exception:
            pass
    bundle_path_for_pointers: Union[ValidationBundle, str, Path] = bundle_or_path
    if isinstance(bundle_or_path, ValidationBundle) and evidence.get("bundle_path"):
        bundle_path_for_pointers = evidence["bundle_path"]
    elif isinstance(bundle_or_path, ValidationBundle) and evidence.get("validation_bundle_path"):
        bundle_path_for_pointers = evidence["validation_bundle_path"]

    # Phase 1: candidate/accepted require eligibility report and promote_to_* (no raw update_status)
    if target_status in ("candidate", "accepted") and decision.status == "accepted":
        report = evaluate_eligibility(bundle, target_status, rc_summary=rc_summary)
        if not report.passed:
            return PromotionDecision(
                status="rejected",
                reasons=report.blockers,
                metrics_snapshot=decision.metrics_snapshot,
                warnings=report.warnings,
            )
        computed_at_utc = now_utc_iso()
        eligibility_report_id = (
            f"elig_{hashlib.sha256((candidate_id + target_status + computed_at_utc).encode()).hexdigest()[:16]}"
        )
        insert_eligibility_report(
            conn,
            eligibility_report_id,
            candidate_id,
            target_status,
            True,
            json.dumps(report.blockers, sort_keys=True),
            json.dumps(report.warnings, sort_keys=True),
            computed_at_utc,
            run_key=report.run_key or None,
            run_instance_id=report.run_instance_id or None,
            dataset_id_v2=report.dataset_id_v2 or None,
            engine_version=report.engine_version or None,
            config_version=report.config_version or None,
        )
        if target_status == "candidate":
            promote_to_candidate(
                conn,
                candidate_id,
                eligibility_report_id,
                reason="; ".join(decision.reasons) if decision.reasons else None,
            )
        else:
            promote_to_accepted(
                conn,
                candidate_id,
                eligibility_report_id,
                reason="; ".join(decision.reasons) if decision.reasons else None,
            )
    else:
        # Only exploratory/rejected can be written via update_status; do not write candidate/accepted without eligibility
        status_to_write = decision.status if decision.status in ("exploratory", "rejected") else "exploratory"
        update_status(
            conn, candidate_id, status_to_write, reason="; ".join(decision.reasons) if decision.reasons else None
        )

    payload: Dict[str, Any] = {
        "status": decision.status,
        "reasons": decision.reasons,
        "metrics_snapshot": decision.metrics_snapshot,
        "thresholds_used": _thresholds_snapshot(
            effective_thresholds, allow_missing_execution_evidence=allow_missing_execution_evidence
        ),
        "artifact_pointers": _artifact_pointers(bundle_path_for_pointers, evidence),
    }
    if getattr(decision, "warnings", None):
        payload["warnings"] = decision.warnings
    record_event(conn, candidate_id, "evaluated", payload)
    return decision
