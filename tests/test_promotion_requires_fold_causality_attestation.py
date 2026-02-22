"""
Promotion gatekeeper: candidate/accepted require valid fold_causality_attestation when walk-forward used.
Exploratory unchanged; no attestation required when not walk-forward.
"""

from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.contracts.schema_versions import (
    SEED_DERIVATION_SCHEMA_VERSION,
    VALIDATION_BUNDLE_SCHEMA_VERSION,
)
from crypto_analyzer.fold_causality.attestation import (
    FOLD_CAUSALITY_ATTESTATION_SCHEMA_VERSION,
    build_fold_causality_attestation,
)
from crypto_analyzer.fold_causality.folds import SplitPlan
from crypto_analyzer.promotion import evaluate_eligibility
from crypto_analyzer.validation_bundle import ValidationBundle


def _bundle_with_meta(meta: dict) -> ValidationBundle:
    return ValidationBundle(
        run_id="run1",
        dataset_id="ds1",
        signal_name="sig",
        freq="1h",
        horizons=[1],
        ic_summary_by_horizon={1: {"mean_ic": 0.03, "t_stat": 3.0, "n_obs": 200}},
        ic_decay_table=[],
        meta=meta,
    )


def _eligibility_meta(**overrides):
    base = {
        "validation_bundle_schema_version": VALIDATION_BUNDLE_SCHEMA_VERSION,
        "dataset_id_v2": "ds2v2",
        "dataset_hash_algo": "sqlite_logical_v2",
        "dataset_hash_mode": "STRICT",
        "run_key": "rk1",
        "engine_version": "v1",
        "config_version": "cfg1",
        "seed_version": SEED_DERIVATION_SCHEMA_VERSION,
    }
    base.update(overrides)
    return base


def _valid_attestation() -> dict:
    return build_fold_causality_attestation(
        run_key="rk1",
        dataset_id_v2="ds2v2",
        split_plan=SplitPlan(folds=[], split_plan_schema_version=1),
        transforms_used=[],
        checks={
            "train_only_fit_enforced": True,
            "purge_applied": True,
            "embargo_applied": True,
            "no_future_rows_in_fit": True,
        },
    )


def test_candidate_blocked_when_walk_forward_used_but_attestation_missing():
    """Candidate: walk_forward_used (or attestation_path) but no fold_causality_attestation -> blockers."""
    meta = _eligibility_meta(walk_forward_used=True)
    bundle = _bundle_with_meta(meta)
    report = evaluate_eligibility(bundle, "candidate")
    assert not report.passed
    assert any("fold_causality" in b for b in report.blockers)


def test_accepted_blocked_when_attestation_missing():
    """Accepted: walk_forward_used but attestation missing -> blockers."""
    meta = _eligibility_meta(fold_causality_attestation_path="fold_causality_attestation.json")
    bundle = _bundle_with_meta(meta)
    report = evaluate_eligibility(bundle, "accepted")
    assert not report.passed
    assert any("fold_causality" in b for b in report.blockers)


def test_accepted_blocked_when_attestation_invalid():
    """Accepted: attestation present but enforcement check false -> blockers."""
    att = _valid_attestation()
    att["enforcement_checks"]["no_future_rows_in_fit"] = False
    meta = _eligibility_meta(
        walk_forward_used=True,
        fold_causality_attestation_schema_version=FOLD_CAUSALITY_ATTESTATION_SCHEMA_VERSION,
        fold_causality_attestation=att,
    )
    bundle = _bundle_with_meta(meta)
    report = evaluate_eligibility(bundle, "accepted")
    assert not report.passed
    assert any("no_future_rows_in_fit" in b for b in report.blockers)


def test_candidate_accepted_pass_when_valid_attestation():
    """Candidate and accepted pass when walk_forward_used and valid attestation in meta."""
    att = _valid_attestation()
    meta = _eligibility_meta(
        walk_forward_used=True,
        fold_causality_attestation_schema_version=FOLD_CAUSALITY_ATTESTATION_SCHEMA_VERSION,
        fold_causality_attestation=att,
    )
    bundle = _bundle_with_meta(meta)
    for level in ("candidate", "accepted"):
        report = evaluate_eligibility(bundle, level)
        assert report.passed, f"level={level} blockers={report.blockers}"


def test_exploratory_unchanged_without_attestation():
    """Exploratory: no attestation required; pass even with walk_forward_used and no attestation."""
    meta = _eligibility_meta(walk_forward_used=True)
    bundle = _bundle_with_meta(meta)
    report = evaluate_eligibility(bundle, "exploratory")
    assert report.passed


def test_candidate_passes_when_not_walk_forward_and_no_attestation():
    """Candidate: when walk_forward_used and attestation_path are absent, attestation not required."""
    meta = _eligibility_meta()
    assert "walk_forward_used" not in meta
    assert "fold_causality_attestation_path" not in meta
    bundle = _bundle_with_meta(meta)
    report = evaluate_eligibility(bundle, "candidate")
    assert report.passed, report.blockers
