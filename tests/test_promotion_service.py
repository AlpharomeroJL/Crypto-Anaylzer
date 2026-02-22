"""Promotion service: evaluate_and_record deterministic and updates store."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from crypto_analyzer.contracts.schema_versions import (
    RC_SUMMARY_SCHEMA_VERSION,
    VALIDATION_BUNDLE_SCHEMA_VERSION,
)
from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.db.migrations_phase3 import run_migrations_phase3
from crypto_analyzer.promotion.gating import ThresholdConfig
from crypto_analyzer.promotion.service import evaluate_and_record
from crypto_analyzer.promotion.store_sqlite import create_candidate, get_candidate, get_events
from crypto_analyzer.validation_bundle import ValidationBundle


def _minimal_bundle(
    mean_ic: float = 0.03,
    t_stat: float = 3.0,
    with_eligibility_meta: bool = False,
) -> ValidationBundle:
    meta = {}
    if with_eligibility_meta:
        meta = {
            "validation_bundle_schema_version": VALIDATION_BUNDLE_SCHEMA_VERSION,
            "dataset_id_v2": "ds2v2",
            "dataset_hash_algo": "sqlite_logical_v2",
            "dataset_hash_mode": "STRICT",
            "run_key": "rk16",
            "engine_version": "abc",
            "config_version": "cfg1",
            "research_spec_version": "1",
        }
    return ValidationBundle(
        run_id="run1",
        dataset_id="ds1",
        signal_name="sig_a",
        freq="1h",
        horizons=[1],
        ic_summary_by_horizon={1: {"mean_ic": mean_ic, "t_stat": t_stat, "n_obs": 200}},
        ic_decay_table=[],
        meta=meta,
    )


@pytest.fixture
def conn_with_promotion():
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        run_migrations_phase3(conn, path)
        yield conn
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)


def test_evaluate_and_record_accepted(conn_with_promotion):
    """Phase 1: accepted requires target_status=accepted and bundle with eligibility meta (dataset_id_v2, run_key, etc.)."""
    conn = conn_with_promotion
    cid = create_candidate(
        conn,
        dataset_id="ds1",
        run_id="run1",
        signal_name="sig_a",
        horizon=1,
        config_hash="x",
        git_commit="y",
    )
    thresholds = ThresholdConfig(ic_mean_min=0.02, tstat_min=2.0, require_reality_check=False)
    bundle = _minimal_bundle(mean_ic=0.03, t_stat=3.0, with_eligibility_meta=True)
    decision = evaluate_and_record(
        conn,
        cid,
        thresholds,
        bundle,
        target_status="accepted",
        allow_missing_execution_evidence=True,
    )
    assert decision.status == "accepted"
    row = get_candidate(conn, cid)
    assert row["status"] == "accepted"
    events = get_events(conn, cid)
    eval_events = [e for e in events if e["event_type"] == "evaluated"]
    assert len(eval_events) == 1
    payload = json.loads(eval_events[0]["payload_json"])
    assert payload.get("status") == "accepted"
    assert "thresholds_used" in payload
    assert "artifact_pointers" in payload
    assert "metrics_snapshot" in payload
    assert payload["thresholds_used"].get("ic_mean_min") == 0.02


def test_e2e_promotion_with_rw_strict_eligibility_persisted_and_direct_update_blocked(conn_with_promotion, monkeypatch):
    """E2E: RW enabled + STRICT hash; promotion via promote_to_accepted; eligibility report persisted; direct SQL update to candidate fails (trigger)."""
    monkeypatch.setenv("CRYPTO_ANALYZER_ENABLE_ROMANOWOLF", "1")
    conn = conn_with_promotion
    cid = create_candidate(
        conn,
        dataset_id="ds1",
        run_id="run1",
        signal_name="sig_a",
        horizon=1,
        config_hash="x",
        git_commit="y",
    )
    thresholds = ThresholdConfig(ic_mean_min=0.02, tstat_min=2.0, require_reality_check=False)
    meta = {
        "validation_bundle_schema_version": VALIDATION_BUNDLE_SCHEMA_VERSION,
        "dataset_id_v2": "ds2v2",
        "dataset_hash_algo": "sqlite_logical_v2",
        "dataset_hash_mode": "STRICT",
        "run_key": "rk16",
        "engine_version": "abc",
        "config_version": "cfg1",
        "research_spec_version": "1",
        "rw_enabled": True,
        "rw_adjusted_p_values": {"sig_a|1": 0.03},
    }
    rc_summary = {
        "rc_summary_schema_version": RC_SUMMARY_SCHEMA_VERSION,
        "rw_enabled": True,
        "rw_adjusted_p_values": {"sig_a|1": 0.03},
        "hypothesis_ids": ["sig_a|1"],
        "actual_n_sim": 100,
        "requested_n_sim": 100,
    }
    bundle = ValidationBundle(
        run_id="run1",
        dataset_id="ds1",
        signal_name="sig_a",
        freq="1h",
        horizons=[1],
        ic_summary_by_horizon={1: {"mean_ic": 0.03, "t_stat": 3.0, "n_obs": 200}},
        ic_decay_table=[],
        meta=meta,
    )
    decision = evaluate_and_record(
        conn,
        cid,
        thresholds,
        bundle,
        target_status="accepted",
        rc_summary=rc_summary,
        allow_missing_execution_evidence=True,
    )
    assert decision.status == "accepted"
    row = get_candidate(conn, cid)
    assert row["status"] == "accepted"
    eligibility_report_id = row.get("eligibility_report_id")
    assert eligibility_report_id, "eligibility_report_id must be set when status=accepted"
    cur = conn.execute(
        "SELECT eligibility_report_id, candidate_id, level, passed FROM eligibility_reports WHERE candidate_id = ?",
        (cid,),
    )
    report_row = cur.fetchone()
    assert report_row is not None, "eligibility report must be persisted"
    assert report_row[2] == "accepted" and report_row[3] == 1
    # Direct SQL update to candidate without eligibility_report_id must fail (trigger)
    cid2 = create_candidate(
        conn, dataset_id="ds1", run_id="run2", signal_name="sig_b", horizon=1, config_hash="x", git_commit="y"
    )
    conn.commit()
    try:
        conn.execute("UPDATE promotion_candidates SET status = ? WHERE candidate_id = ?", ("candidate", cid2))
        conn.commit()
    except (sqlite3.IntegrityError, sqlite3.OperationalError) as e:
        assert "eligibility" in str(e).lower() or "abort" in str(e).lower()
        return
    assert False, "Expected trigger to block direct UPDATE to status=candidate without eligibility_report_id"


def test_evaluate_and_record_rejected_low_ic(conn_with_promotion):
    conn = conn_with_promotion
    cid = create_candidate(
        conn,
        dataset_id="ds1",
        run_id="run1",
        signal_name="sig_a",
        horizon=1,
        config_hash="x",
        git_commit="y",
    )
    thresholds = ThresholdConfig(ic_mean_min=0.05, tstat_min=2.0)
    bundle = _minimal_bundle(mean_ic=0.01, t_stat=1.0)
    decision = evaluate_and_record(conn, cid, thresholds, bundle)
    assert decision.status == "rejected"
    assert any("mean_ic" in r for r in decision.reasons)
    row = get_candidate(conn, cid)
    assert row["status"] == "rejected"


def test_evaluate_and_record_candidate_not_found(conn_with_promotion):
    conn = conn_with_promotion
    thresholds = ThresholdConfig()
    bundle = _minimal_bundle()
    decision = evaluate_and_record(conn, "nonexistent_id", thresholds, bundle)
    assert decision.status == "rejected"
    assert any("not found" in r for r in decision.reasons)


def test_sweep_candidate_requires_rc_for_acceptance(conn_with_promotion):
    """Candidates with family_id cannot become accepted without RC when require_reality_check=False in config."""
    conn = conn_with_promotion
    cid = create_candidate(
        conn,
        dataset_id="ds1",
        run_id="run1",
        signal_name="sig_a",
        horizon=1,
        config_hash="x",
        git_commit="y",
        family_id="rcfam_abc123",
    )
    thresholds = ThresholdConfig(ic_mean_min=0.02, tstat_min=2.0, require_reality_check=False)
    bundle = _minimal_bundle(mean_ic=0.03, t_stat=3.0)
    # No rc_summary -> effective require_reality_check=True forces rejection (no rc_p_value)
    decision = evaluate_and_record(conn, cid, thresholds, bundle)
    assert decision.status == "rejected"
    assert any("reality_check" in r.lower() or "rc_p_value" in r.lower() for r in decision.reasons)
    row = get_candidate(conn, cid)
    assert row["status"] == "rejected"


def test_sweep_candidate_accepted_when_rc_passes(conn_with_promotion):
    """Sweep candidate with family_id is accepted when RC summary passes; Phase 1 requires target_status and eligibility meta."""
    conn = conn_with_promotion
    cid = create_candidate(
        conn,
        dataset_id="ds1",
        run_id="run1",
        signal_name="sig_a",
        horizon=1,
        config_hash="x",
        git_commit="y",
        family_id="rcfam_xyz",
    )
    thresholds = ThresholdConfig(ic_mean_min=0.02, tstat_min=2.0, require_reality_check=False, max_rc_p_value=0.05)
    bundle = _minimal_bundle(mean_ic=0.03, t_stat=3.0, with_eligibility_meta=True)
    rc_summary = {"rc_summary_schema_version": RC_SUMMARY_SCHEMA_VERSION, "rc_p_value": 0.03}
    decision = evaluate_and_record(
        conn,
        cid,
        thresholds,
        bundle,
        rc_summary=rc_summary,
        target_status="accepted",
        allow_missing_execution_evidence=True,
    )
    assert decision.status == "accepted"
    row = get_candidate(conn, cid)
    assert row["status"] == "accepted"


def test_reject_when_target_candidate_and_execution_evidence_missing_override_false(conn_with_promotion):
    """When target_status is accepted and no execution evidence and override False -> rejected."""
    conn = conn_with_promotion
    cid = create_candidate(
        conn,
        dataset_id="ds1",
        run_id="run1",
        signal_name="sig_a",
        horizon=1,
        config_hash="x",
        git_commit="y",
        evidence={"bundle_path": "/fake/bundle.json"},
    )
    thresholds = ThresholdConfig(ic_mean_min=0.02, tstat_min=2.0, require_execution_evidence=False)
    bundle = _minimal_bundle(mean_ic=0.03, t_stat=3.0, with_eligibility_meta=True)
    decision = evaluate_and_record(
        conn,
        cid,
        thresholds,
        bundle,
        evidence_base_path=Path("/fake"),
        target_status="accepted",
        allow_missing_execution_evidence=False,
    )
    assert decision.status == "rejected"
    assert any("execution evidence" in r.lower() for r in decision.reasons)


def test_accept_when_override_true_records_override_in_event(conn_with_promotion):
    """When allow_missing_execution_evidence=True, accept and record override in event payload. Phase 1: no direct status update."""
    conn = conn_with_promotion
    cid = create_candidate(
        conn,
        dataset_id="ds1",
        run_id="run1",
        signal_name="sig_a",
        horizon=1,
        config_hash="x",
        git_commit="y",
        evidence={"bundle_path": "/fake/bundle.json"},
    )
    thresholds = ThresholdConfig(ic_mean_min=0.02, tstat_min=2.0, require_execution_evidence=False)
    bundle = _minimal_bundle(mean_ic=0.03, t_stat=3.0, with_eligibility_meta=True)
    decision = evaluate_and_record(
        conn,
        cid,
        thresholds,
        bundle,
        evidence_base_path=Path("/fake"),
        target_status="accepted",
        allow_missing_execution_evidence=True,
    )
    assert decision.status == "accepted"
    assert any("allow_missing_execution_evidence" in w for w in decision.warnings)
    events = get_events(conn, cid)
    eval_ev = [e for e in events if e["event_type"] == "evaluated"]
    assert len(eval_ev) == 1
    payload = json.loads(eval_ev[0]["payload_json"])
    assert payload.get("thresholds_used", {}).get("allow_missing_execution_evidence") is True
    assert any("allow_missing" in w for w in payload.get("warnings", []))
