"""
Single governance entrypoint: evaluate_and_record and promote.
Phase 3 A3. All status transitions to candidate/accepted must go through this API.
Logs every evaluate/promote to governance_events (append-only).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from crypto_analyzer.promotion.gating import PromotionDecision, ThresholdConfig
from crypto_analyzer.promotion.service import evaluate_and_record as _service_evaluate_and_record

# Store layer: persistence only
from crypto_analyzer.promotion.store_sqlite import (
    get_candidate,
    promote_to_accepted,
    promote_to_candidate,
)
from crypto_analyzer.timeutils import now_utc_iso
from crypto_analyzer.validation_bundle import ValidationBundle

try:
    from crypto_analyzer.db.governance_events import (
        append_governance_event,
        governance_events_table_exists,
    )
except ImportError:
    governance_events_table_exists = lambda conn: False  # noqa: E731
    append_governance_event = None


def evaluate_and_record(
    conn: sqlite3.Connection,
    candidate_id: str,
    thresholds: ThresholdConfig,
    bundle_or_path: Union[ValidationBundle, str, Path],
    *,
    regime_summary_df=None,
    rc_summary: Optional[Dict[str, Any]] = None,
    evidence_base_path: Optional[Union[str, Path]] = None,
    target_status: str = "exploratory",
    allow_missing_execution_evidence: bool = False,
    actor: str = "cli",
) -> Tuple[PromotionDecision, Optional[str]]:
    """
    Evaluate candidate and record decision. All promotion status changes go through here.
    Returns (decision, eligibility_report_id when created for candidate/accepted, else None).
    Appends to governance_events when table exists.
    """
    decision = _service_evaluate_and_record(
        conn,
        candidate_id,
        thresholds,
        bundle_or_path,
        regime_summary_df=regime_summary_df,
        rc_summary=rc_summary,
        evidence_base_path=evidence_base_path,
        target_status=target_status,
        allow_missing_execution_evidence=allow_missing_execution_evidence,
    )
    eligibility_report_id: Optional[str] = None
    run_key: Optional[str] = None
    dataset_id_v2: Optional[str] = None
    row = get_candidate(conn, candidate_id)
    if row:
        eligibility_report_id = row.get("eligibility_report_id") or None
        run_key = row.get("run_key") or None
        dataset_id_v2 = row.get("dataset_id_v2") or None
    if not run_key and row and row.get("evidence_json"):
        import json

        try:
            ev = json.loads(row["evidence_json"])
            run_key = ev.get("run_key")
            dataset_id_v2 = dataset_id_v2 or ev.get("dataset_id_v2")
        except Exception:
            pass
    if governance_events_table_exists(conn) and append_governance_event is not None:
        try:
            append_governance_event(
                conn,
                timestamp=now_utc_iso(),
                actor=actor,
                action="evaluate",
                candidate_id=candidate_id,
                eligibility_report_id=eligibility_report_id or "",
                run_key=run_key or "",
                dataset_id_v2=dataset_id_v2 or "",
            )
        except Exception:
            pass
    if (
        decision.status in ("candidate", "accepted")
        and eligibility_report_id
        and governance_events_table_exists(conn)
        and append_governance_event is not None
    ):
        try:
            append_governance_event(
                conn,
                timestamp=now_utc_iso(),
                actor=actor,
                action="promote",
                candidate_id=candidate_id,
                eligibility_report_id=eligibility_report_id,
                run_key=run_key or "",
                dataset_id_v2=dataset_id_v2 or "",
            )
        except Exception:
            pass
    return decision, eligibility_report_id


def promote(
    conn: sqlite3.Connection,
    candidate_id: str,
    target_status: str,
    eligibility_report_id: str,
    *,
    reason: Optional[str] = None,
    actor: str = "cli",
) -> None:
    """
    Promote candidate to target_status (candidate or accepted) with existing eligibility_report_id.
    All such transitions must go through this API. Appends to governance_events when table exists.
    """
    if target_status == "candidate":
        promote_to_candidate(conn, candidate_id, eligibility_report_id, reason=reason)
    elif target_status == "accepted":
        promote_to_accepted(conn, candidate_id, eligibility_report_id, reason=reason)
    else:
        raise ValueError(f"promote() only supports target_status 'candidate' or 'accepted', got {target_status!r}")
    run_key = ""
    dataset_id_v2 = ""
    row = get_candidate(conn, candidate_id)
    if row and row.get("evidence_json"):
        import json

        try:
            ev = json.loads(row["evidence_json"])
            run_key = ev.get("run_key") or ""
            dataset_id_v2 = ev.get("dataset_id_v2") or ""
        except Exception:
            pass
    if governance_events_table_exists(conn) and append_governance_event is not None:
        try:
            append_governance_event(
                conn,
                timestamp=now_utc_iso(),
                actor=actor,
                action="promote",
                candidate_id=candidate_id,
                eligibility_report_id=eligibility_report_id,
                run_key=run_key,
                dataset_id_v2=dataset_id_v2,
            )
        except Exception:
            pass
