"""Promotion service: evaluate_and_record deterministic and updates store."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.db.migrations_phase3 import run_migrations_phase3
from crypto_analyzer.promotion.gating import ThresholdConfig
from crypto_analyzer.promotion.service import evaluate_and_record
from crypto_analyzer.promotion.store_sqlite import create_candidate, get_candidate, get_events
from crypto_analyzer.validation_bundle import ValidationBundle


def _minimal_bundle(mean_ic: float = 0.03, t_stat: float = 3.0) -> ValidationBundle:
    return ValidationBundle(
        run_id="run1",
        dataset_id="ds1",
        signal_name="sig_a",
        freq="1h",
        horizons=[1],
        ic_summary_by_horizon={1: {"mean_ic": mean_ic, "t_stat": t_stat, "n_obs": 200}},
        ic_decay_table=[],
        meta={},
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
    bundle = _minimal_bundle(mean_ic=0.03, t_stat=3.0)
    decision = evaluate_and_record(conn, cid, thresholds, bundle)
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
    """Sweep candidate with family_id is accepted when RC summary passes and require_reality_check=False (enforced)."""
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
    bundle = _minimal_bundle(mean_ic=0.03, t_stat=3.0)
    rc_summary = {"rc_p_value": 0.03}
    decision = evaluate_and_record(conn, cid, thresholds, bundle, rc_summary=rc_summary)
    assert decision.status == "accepted"
    row = get_candidate(conn, cid)
    assert row["status"] == "accepted"


def test_reject_when_target_candidate_and_execution_evidence_missing_override_false(conn_with_promotion):
    """When target_status is candidate and no execution evidence and override False -> rejected."""
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
    # Candidate status so target is "accepted"; no execution_evidence_path in evidence
    conn.execute("UPDATE promotion_candidates SET status = ? WHERE candidate_id = ?", ("candidate", cid))
    conn.commit()
    thresholds = ThresholdConfig(ic_mean_min=0.02, tstat_min=2.0, require_execution_evidence=False)
    bundle = _minimal_bundle(mean_ic=0.03, t_stat=3.0)
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
    """When allow_missing_execution_evidence=True, accept and record override in event payload."""
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
    conn.execute("UPDATE promotion_candidates SET status = ? WHERE candidate_id = ?", ("candidate", cid))
    conn.commit()
    thresholds = ThresholdConfig(ic_mean_min=0.02, tstat_min=2.0, require_execution_evidence=False)
    bundle = _minimal_bundle(mean_ic=0.03, t_stat=3.0)
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
