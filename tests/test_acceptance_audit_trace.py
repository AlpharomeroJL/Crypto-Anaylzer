"""
Phase 3.5 A4: E2E accepted promotion produces full audit trace (eligibility, governance_events, artifact_lineage).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from crypto_analyzer.contracts.schema_versions import (
    RC_SUMMARY_SCHEMA_VERSION,
    VALIDATION_BUNDLE_SCHEMA_VERSION,
)
from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.db.migrations_phase3 import run_migrations_phase3
from crypto_analyzer.governance import evaluate_and_record
from crypto_analyzer.governance.audit import trace_acceptance
from crypto_analyzer.governance.audit_invariants import assert_acceptance_auditable
from crypto_analyzer.promotion.gating import ThresholdConfig
from crypto_analyzer.promotion.store_sqlite import create_candidate
from crypto_analyzer.store.sqlite_session import sqlite_conn
from crypto_analyzer.timeutils import now_utc_iso
from crypto_analyzer.validation_bundle import ValidationBundle


def _write_bundle(path: Path, run_id: str = "run_audit") -> None:
    meta = {
        "validation_bundle_schema_version": VALIDATION_BUNDLE_SCHEMA_VERSION,
        "dataset_id_v2": "ds_audit",
        "dataset_hash_algo": "sqlite_logical_v2",
        "dataset_hash_mode": "STRICT",
        "run_key": "rk_audit",
        "run_instance_id": run_id,
        "engine_version": "v1",
        "config_version": "c1",
        "seed_version": 1,
    }
    bundle = ValidationBundle(
        run_id=run_id,
        dataset_id="ds_audit",
        signal_name="sig",
        freq="1h",
        horizons=[1],
        ic_summary_by_horizon={1: {"mean_ic": 0.04, "t_stat": 3.0, "n_obs": 200}},
        ic_decay_table=[],
        meta=meta,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bundle.to_dict(), f, sort_keys=True)


def test_acceptance_audit_trace_includes_eligibility_governance_lineage():
    """Minimal E2E: create candidate, evaluate to accepted, add lineage row, then trace and assert invariant."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        db_path = tmp / "audit.sqlite"
        bundle_path = tmp / "reports" / "bundle.json"
        run_id = "run_audit_e2e"
        _write_bundle(bundle_path, run_id=run_id)

        with sqlite_conn(db_path) as conn:
            run_migrations(conn, db_path)
            run_migrations_phase3(conn, db_path)
            evidence = {
                "bundle_path": str(bundle_path),
                "validation_bundle_path": str(bundle_path),
                "run_instance_id": run_id,
            }
            cid = create_candidate(
                conn,
                dataset_id="ds_audit",
                run_id=run_id,
                signal_name="sig",
                horizon=1,
                config_hash="x",
                git_commit="y",
                evidence=evidence,
            )

        thresholds = ThresholdConfig(ic_mean_min=0.02, tstat_min=2.0, require_reality_check=True, max_rc_p_value=0.05)
        rc_summary = {"rc_summary_schema_version": RC_SUMMARY_SCHEMA_VERSION, "rc_p_value": 0.02}

        with sqlite_conn(db_path) as conn:
            decision, _ = evaluate_and_record(
                conn,
                cid,
                thresholds,
                str(bundle_path),
                rc_summary=rc_summary,
                evidence_base_path=bundle_path.parent,
                target_status="accepted",
                allow_missing_execution_evidence=True,
            )
        assert decision.status == "accepted"

        # Simulate pipeline having written one artifact_lineage row for this run
        with sqlite_conn(db_path) as conn:
            from crypto_analyzer.db.lineage import lineage_tables_exist, write_artifact_lineage

            if lineage_tables_exist(conn):
                write_artifact_lineage(
                    conn,
                    artifact_id="manifest_sha_placeholder",
                    run_instance_id=run_id,
                    run_key="rk_audit",
                    dataset_id_v2="ds_audit",
                    artifact_type="manifest",
                    relative_path="manifest.json",
                    sha256="abc123",
                    created_utc=now_utc_iso(),
                )

        with sqlite_conn(db_path) as conn:
            trace = trace_acceptance(conn, cid)
            assert trace.candidate_id == cid
            assert trace.eligibility_report_id is not None
            assert any(e.get("action") == "evaluate" for e in trace.governance_events)
            assert any(e.get("action") == "promote" for e in trace.governance_events)
            assert len(trace.artifact_lineage) >= 1

            assert_acceptance_auditable(conn, cid)
