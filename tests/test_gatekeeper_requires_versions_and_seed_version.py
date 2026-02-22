"""Phase 3 A6: Gatekeeper blocks candidate/accepted when engine_version, config_version, or schema versions missing."""

from __future__ import annotations

from crypto_analyzer.promotion.gating import evaluate_eligibility
from crypto_analyzer.validation_bundle import ValidationBundle


def test_eligibility_rejected_when_engine_version_missing():
    bundle = ValidationBundle(
        run_id="r1",
        dataset_id="d1",
        signal_name="s1",
        freq="1h",
        horizons=[1],
        ic_summary_by_horizon={1: {"mean_ic": 0.05, "t_stat": 3.0, "n_obs": 100}},
        ic_decay_table=[],
        meta={
            "dataset_id_v2": "dsv2",
            "dataset_hash_algo": "sqlite_logical_v2",
            "dataset_hash_mode": "STRICT",
            "run_key": "rk1",
            "engine_version": "",
            "config_version": "c1",
            "validation_bundle_schema_version": 1,
        },
    )
    report = evaluate_eligibility(bundle, "candidate", rc_summary=None)
    assert report.passed is False
    assert any("engine_version" in b for b in report.blockers)


def test_eligibility_rejected_when_config_version_missing():
    bundle = ValidationBundle(
        run_id="r1",
        dataset_id="d1",
        signal_name="s1",
        freq="1h",
        horizons=[1],
        ic_summary_by_horizon={1: {"mean_ic": 0.05, "t_stat": 3.0, "n_obs": 100}},
        ic_decay_table=[],
        meta={
            "dataset_id_v2": "dsv2",
            "dataset_hash_algo": "sqlite_logical_v2",
            "dataset_hash_mode": "STRICT",
            "run_key": "rk1",
            "engine_version": "e1",
            "config_version": None,
            "validation_bundle_schema_version": 1,
        },
    )
    report = evaluate_eligibility(bundle, "candidate", rc_summary=None)
    assert report.passed is False
    assert any("config_version" in b for b in report.blockers)


def test_eligibility_passed_when_versions_present():
    bundle = ValidationBundle(
        run_id="r1",
        dataset_id="d1",
        signal_name="s1",
        freq="1h",
        horizons=[1],
        ic_summary_by_horizon={1: {"mean_ic": 0.05, "t_stat": 3.0, "n_obs": 100}},
        ic_decay_table=[],
        meta={
            "dataset_id_v2": "dsv2",
            "dataset_hash_algo": "sqlite_logical_v2",
            "dataset_hash_mode": "STRICT",
            "run_key": "rk1",
            "engine_version": "e1",
            "config_version": "c1",
            "validation_bundle_schema_version": 1,
            "seed_version": 1,
        },
    )
    report = evaluate_eligibility(bundle, "candidate", rc_summary=None)
    assert report.passed is True
