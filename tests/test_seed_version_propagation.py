"""
Phase 3.5 A5: seed_version propagation — bundle meta, RC summary, fold attestation.
Candidate/accepted requires seed_version in bundle meta; rc_summary contains seed_version and matches.
"""

from __future__ import annotations

import json
from pathlib import Path

from crypto_analyzer.contracts.schema_versions import SEED_DERIVATION_SCHEMA_VERSION
from crypto_analyzer.contracts.validation_bundle_contract import validate_bundle_for_level
from crypto_analyzer.core.context import RunContext
from crypto_analyzer.pipelines.research_pipeline import run_research_pipeline


def test_candidate_requires_seed_version_in_bundle_meta():
    """Candidate/accepted requires seed_version in bundle meta; validate_bundle_for_level enforces it."""
    meta_without = {
        "run_key": "r",
        "dataset_id_v2": "d",
        "engine_version": "v",
        "config_version": "c",
        "dataset_hash_algo": "sqlite_logical_v2",
        "dataset_hash_mode": "STRICT",
    }
    ok, reasons, _ = validate_bundle_for_level({"meta": meta_without}, "candidate")
    assert not ok
    assert any("seed_version" in r for r in reasons)

    meta_with = {
        **meta_without,
        "validation_bundle_schema_version": 1,
        "seed_version": SEED_DERIVATION_SCHEMA_VERSION,
    }
    ok2, reasons2, _ = validate_bundle_for_level({"meta": meta_with}, "candidate")
    assert ok2, reasons2


def test_rc_summary_contains_seed_version_when_rc_enabled():
    """When reality check runs, rc_summary contains seed_version matching bundle meta."""
    run_ctx = RunContext(
        run_key="rk_rc",
        run_instance_id="run_rc",
        dataset_id_v2="ds1",
        engine_version="v1",
        config_version="c1",
        seed_version=SEED_DERIVATION_SCHEMA_VERSION,
    )
    config = {
        "out_dir": "artifacts/research",
        "dataset_id": "demo",
        "rc_n_sim": 20,
    }
    result = run_research_pipeline(
        config,
        "hyp_rc",
        "fam_rc",
        run_context=run_ctx,
        enable_reality_check=True,
    )
    assert result.bundle_dir
    rc_path = Path(result.bundle_dir) / "rc_summary.json"
    assert rc_path.exists(), "rc_summary.json should exist when RC enabled"
    rc = json.loads(rc_path.read_text(encoding="utf-8"))
    assert "seed_version" in rc
    assert rc["seed_version"] == SEED_DERIVATION_SCHEMA_VERSION


def test_fold_attestation_contains_seed_version():
    """Fold causality attestation built by build_fold_causality_attestation includes seed_version."""
    from crypto_analyzer.fold_causality.attestation import build_fold_causality_attestation
    from crypto_analyzer.fold_causality.folds import FoldSpec, SplitPlan

    fold = FoldSpec(
        fold_id="f0",
        train_start_ts="2025-01-01",
        train_end_ts="2025-01-01",
        test_start_ts="2025-01-02",
        test_end_ts="2025-01-03",
        purge_gap_bars=0,
        embargo_bars=0,
        asof_lag_bars=0,
    )
    plan = SplitPlan(folds=[fold], split_plan_schema_version=1)
    att = build_fold_causality_attestation(
        run_key="rk",
        dataset_id_v2="ds1",
        split_plan=plan,
        transforms_used=[],
        checks={
            "train_only_fit_enforced": True,
            "purge_applied": True,
            "embargo_applied": True,
            "no_future_rows_in_fit": True,
        },
        seed_root=12345,
        seed_salt="fold_splits",
        seed_version=SEED_DERIVATION_SCHEMA_VERSION,
    )
    assert "seed_version" in att
    assert att["seed_version"] == SEED_DERIVATION_SCHEMA_VERSION
