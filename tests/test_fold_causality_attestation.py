"""
Fold-causality attestation: required keys, schema version, determinism.
"""

from __future__ import annotations

from crypto_analyzer.fold_causality.attestation import (
    FOLD_CAUSALITY_ATTESTATION_SCHEMA_VERSION,
    build_fold_causality_attestation,
    validate_attestation,
)
from crypto_analyzer.fold_causality.folds import SplitPlan


def test_attestation_has_required_keys():
    """Attestation includes schema version, run_key, dataset_id_v2, split_plan_summary, transforms, enforcement_checks."""
    plan = SplitPlan(folds=[], split_plan_schema_version=1)
    att = build_fold_causality_attestation(
        run_key="rk1",
        dataset_id_v2="ds1",
        split_plan=plan,
        transforms_used=[{"name": "zscore", "kind": "trainable"}],
        checks={
            "train_only_fit_enforced": True,
            "purge_applied": True,
            "embargo_applied": True,
            "no_future_rows_in_fit": True,
        },
    )
    assert att["fold_causality_attestation_schema_version"] == FOLD_CAUSALITY_ATTESTATION_SCHEMA_VERSION
    assert att["run_key"] == "rk1"
    assert att["dataset_id_v2"] == "ds1"
    assert "split_plan_summary" in att
    assert att["split_plan_summary"]["n_folds"] == 0
    assert "transforms" in att
    assert "enforcement_checks" in att
    assert att["enforcement_checks"]["train_only_fit_enforced"] is True
    assert att["enforcement_checks"]["no_future_rows_in_fit"] is True


def test_attestation_schema_version_constant():
    """FOLD_CAUSALITY_ATTESTATION_SCHEMA_VERSION is 1."""
    assert FOLD_CAUSALITY_ATTESTATION_SCHEMA_VERSION == 1


def test_validate_attestation_passes_when_valid():
    """validate_attestation returns (True, []) when all checks true and schema version correct."""
    att = build_fold_causality_attestation(
        run_key="r",
        dataset_id_v2="d",
        split_plan=SplitPlan(folds=[]),
        transforms_used=[],
        checks={
            "train_only_fit_enforced": True,
            "purge_applied": True,
            "embargo_applied": True,
            "no_future_rows_in_fit": True,
        },
    )
    ok, blockers = validate_attestation(att)
    assert ok is True
    assert len(blockers) == 0


def test_validate_attestation_fails_when_check_false():
    """validate_attestation returns (False, blockers) when any enforcement check is not true."""
    att = build_fold_causality_attestation(
        run_key="r",
        dataset_id_v2="d",
        split_plan=SplitPlan(folds=[]),
        transforms_used=[],
        checks={
            "train_only_fit_enforced": True,
            "purge_applied": True,
            "embargo_applied": True,
            "no_future_rows_in_fit": False,
        },
    )
    ok, blockers = validate_attestation(att)
    assert ok is False
    assert any("no_future_rows_in_fit" in b for b in blockers)


def test_validate_attestation_fails_wrong_schema_version():
    """validate_attestation fails when schema version mismatch."""
    att = build_fold_causality_attestation(
        run_key="r",
        dataset_id_v2="d",
        split_plan=SplitPlan(folds=[]),
        transforms_used=[],
        checks={
            "train_only_fit_enforced": True,
            "purge_applied": True,
            "embargo_applied": True,
            "no_future_rows_in_fit": True,
        },
    )
    att["fold_causality_attestation_schema_version"] = 99
    ok, blockers = validate_attestation(att)
    assert ok is False
    assert any("schema_version" in b for b in blockers)


def test_attestation_deterministic_same_inputs():
    """Same inputs -> same attestation (deterministic)."""
    plan = SplitPlan(folds=[], split_plan_schema_version=1)
    att1 = build_fold_causality_attestation(
        run_key="rk",
        dataset_id_v2="ds",
        split_plan=plan,
        transforms_used=[{"name": "a", "kind": "exogenous"}],
        checks={
            "train_only_fit_enforced": True,
            "purge_applied": False,
            "embargo_applied": False,
            "no_future_rows_in_fit": True,
        },
    )
    att2 = build_fold_causality_attestation(
        run_key="rk",
        dataset_id_v2="ds",
        split_plan=plan,
        transforms_used=[{"name": "a", "kind": "exogenous"}],
        checks={
            "train_only_fit_enforced": True,
            "purge_applied": False,
            "embargo_applied": False,
            "no_future_rows_in_fit": True,
        },
    )
    assert att1["run_key"] == att2["run_key"]
    assert att1["fold_causality_attestation_schema_version"] == att2["fold_causality_attestation_schema_version"]
    assert att1["enforcement_checks"] == att2["enforcement_checks"]
