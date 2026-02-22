"""
Audit invariants: assert that an accepted candidate has a complete audit trail.
Phase 3.5 A4. Fail-closed: raises with actionable messages when any required link is missing.
"""

from __future__ import annotations

import sqlite3

from .audit import trace_acceptance


def assert_acceptance_auditable(conn: sqlite3.Connection, candidate_id: str) -> None:
    """
    Raise AssertionError with actionable messages if the candidate does not have a full audit trail.
    Required for candidate/accepted:
    - eligibility_report row exists and passed=1, level matches status
    - at least one governance_event with action 'evaluate' and one with action 'promote' for this candidate
    - at least one artifact_lineage row for the same run (validation bundle manifest or equivalent)
    """
    trace = trace_acceptance(conn, candidate_id)
    errors: list[str] = []

    # Candidate must exist and be accepted (or candidate)
    cur = conn.execute(
        "SELECT status, eligibility_report_id FROM promotion_candidates WHERE candidate_id = ?", (candidate_id,)
    )
    row = cur.fetchone()
    if not row:
        raise AssertionError(f"candidate_id {candidate_id!r} not found in promotion_candidates")
    status, elig_id = row[0], row[1]
    if status not in ("candidate", "accepted"):
        raise AssertionError(f"assert_acceptance_auditable requires status candidate or accepted; got {status!r}")

    if not trace.eligibility_report_id or not elig_id:
        errors.append("eligibility_report_id is missing on promotion_candidates row")
    else:
        cur = conn.execute(
            "SELECT passed, level FROM eligibility_reports WHERE eligibility_report_id = ?",
            (trace.eligibility_report_id,),
        )
        er_row = cur.fetchone()
        if not er_row:
            errors.append(
                f"eligibility_reports row for eligibility_report_id {trace.eligibility_report_id!r} not found"
            )
        else:
            passed, level = er_row[0], er_row[1]
            if passed != 1:
                errors.append("eligibility_reports.passed must be 1 for candidate/accepted")
            if level != status:
                errors.append(f"eligibility_reports.level {level!r} must match status {status!r}")

    actions = [e.get("action") for e in trace.governance_events]
    if "evaluate" not in actions:
        errors.append("at least one governance_event with action 'evaluate' required")
    if "promote" not in actions:
        errors.append("at least one governance_event with action 'promote' required")

    if not trace.artifact_lineage:
        errors.append(
            "at least one artifact_lineage row required for the run (validation bundle manifest or equivalent)"
        )

    if errors:
        raise AssertionError("Acceptance audit invariant failed: " + "; ".join(errors))
