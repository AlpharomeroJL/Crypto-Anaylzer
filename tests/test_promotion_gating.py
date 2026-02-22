"""Promotion gating: evaluate_candidate deterministic; require_regime_robustness toggles regime rule."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.contracts.schema_versions import (
    RC_SUMMARY_SCHEMA_VERSION,
    SEED_DERIVATION_SCHEMA_VERSION,
    VALIDATION_BUNDLE_SCHEMA_VERSION,
)
from crypto_analyzer.promotion import ThresholdConfig, evaluate_candidate, evaluate_eligibility
from crypto_analyzer.validation_bundle import ValidationBundle


def _minimal_bundle(mean_ic: float = 0.03, t_stat: float = 3.0) -> ValidationBundle:
    return ValidationBundle(
        run_id="test_run",
        dataset_id="ds1",
        signal_name="test_signal",
        freq="1h",
        horizons=[1, 4],
        ic_summary_by_horizon={
            1: {"mean_ic": mean_ic, "std_ic": 0.01, "t_stat": t_stat, "hit_rate": 0.52, "n_obs": 200},
            4: {"mean_ic": mean_ic, "std_ic": 0.01, "t_stat": t_stat, "hit_rate": 0.51, "n_obs": 200},
        },
        ic_decay_table=[],
        meta={},
    )


def test_evaluate_candidate_accepts_when_above_thresholds():
    """With default thresholds and no regime robustness, good metrics -> accepted."""
    bundle = _minimal_bundle(mean_ic=0.03, t_stat=3.0)
    cfg = ThresholdConfig(ic_mean_min=0.02, tstat_min=2.5, require_regime_robustness=False)
    decision = evaluate_candidate(bundle, cfg, regime_summary_df=None)
    assert decision.status == "accepted"
    assert len(decision.reasons) == 0


def test_evaluate_candidate_rejects_low_ic():
    """Below ic_mean_min -> rejected."""
    bundle = _minimal_bundle(mean_ic=0.01, t_stat=3.0)
    cfg = ThresholdConfig(ic_mean_min=0.02, require_regime_robustness=False)
    decision = evaluate_candidate(bundle, cfg, regime_summary_df=None)
    assert decision.status == "rejected"
    assert any("mean_ic" in r for r in decision.reasons)


def test_evaluate_candidate_rejects_low_tstat():
    """Below tstat_min -> rejected."""
    bundle = _minimal_bundle(mean_ic=0.03, t_stat=2.0)
    cfg = ThresholdConfig(ic_mean_min=0.02, tstat_min=2.5, require_regime_robustness=False)
    decision = evaluate_candidate(bundle, cfg, regime_summary_df=None)
    assert decision.status == "rejected"
    assert any("t_stat" in r for r in decision.reasons)


def test_require_regime_robustness_off_ignores_regime_summary():
    """With require_regime_robustness=False, regime_summary_df is ignored; good base metrics -> accepted."""
    bundle = _minimal_bundle(mean_ic=0.03, t_stat=3.0)
    cfg = ThresholdConfig(require_regime_robustness=False)
    # Regime summary with one regime below threshold would reject if robustness were on
    regime_df = pd.DataFrame(
        [
            {"regime": "L", "mean_ic": 0.01},
            {"regime": "H", "mean_ic": 0.04},
        ]
    )
    decision = evaluate_candidate(bundle, cfg, regime_summary_df=regime_df)
    assert decision.status == "accepted"


def test_require_regime_robustness_on_rejects_worst_below_min():
    """With require_regime_robustness=True and worst_regime_ic_mean_min set, reject if any regime below."""
    bundle = _minimal_bundle(mean_ic=0.03, t_stat=3.0)
    cfg = ThresholdConfig(
        require_regime_robustness=True,
        worst_regime_ic_mean_min=0.02,
    )
    regime_df = pd.DataFrame(
        [
            {"regime": "L", "mean_ic": 0.01},
            {"regime": "H", "mean_ic": 0.04},
        ]
    )
    decision = evaluate_candidate(bundle, cfg, regime_summary_df=regime_df)
    assert decision.status == "rejected"
    assert any("worst regime" in r for r in decision.reasons)


def test_require_regime_robustness_on_accepts_when_all_above():
    """When all regimes above worst_regime_ic_mean_min and >= 2 regimes, accept."""
    bundle = _minimal_bundle(mean_ic=0.03, t_stat=3.0)
    cfg = ThresholdConfig(
        require_regime_robustness=True,
        worst_regime_ic_mean_min=0.02,
    )
    regime_df = pd.DataFrame(
        [
            {"regime": "L", "mean_ic": 0.025},
            {"regime": "H", "mean_ic": 0.04},
        ]
    )
    decision = evaluate_candidate(bundle, cfg, regime_summary_df=regime_df)
    assert decision.status == "accepted"


def test_require_reality_check_rejects_when_rc_p_value_above_threshold():
    """When require_reality_check=True, reject if rc_p_value > max_rc_p_value."""
    bundle = _minimal_bundle(mean_ic=0.03, t_stat=3.0)
    cfg = ThresholdConfig(require_reality_check=True, max_rc_p_value=0.05)
    rc_summary = {"rc_summary_schema_version": RC_SUMMARY_SCHEMA_VERSION, "rc_p_value": 0.10}
    decision = evaluate_candidate(bundle, cfg, regime_summary_df=None, rc_summary=rc_summary)
    assert decision.status == "rejected"
    assert any("rc_p_value" in r for r in decision.reasons)


def test_require_reality_check_accepts_when_rc_p_value_below_threshold():
    """When require_reality_check=True and rc_p_value <= threshold, no RC reason."""
    bundle = _minimal_bundle(mean_ic=0.03, t_stat=3.0)
    cfg = ThresholdConfig(require_reality_check=True, max_rc_p_value=0.05)
    rc_summary = {"rc_summary_schema_version": RC_SUMMARY_SCHEMA_VERSION, "rc_p_value": 0.02}
    decision = evaluate_candidate(bundle, cfg, regime_summary_df=None, rc_summary=rc_summary)
    assert decision.status == "accepted"


def test_evaluate_candidate_deterministic():
    """Same inputs -> same PromotionDecision (no randomness)."""
    bundle = _minimal_bundle(mean_ic=0.03, t_stat=3.0)
    cfg = ThresholdConfig(require_regime_robustness=False)
    d1 = evaluate_candidate(bundle, cfg, None)
    d2 = evaluate_candidate(bundle, cfg, None)
    assert d1.status == d2.status
    assert d1.reasons == d2.reasons


# --- Phase 1 gatekeeper: evaluate_eligibility ---


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


def test_evaluate_eligibility_blocks_when_run_key_missing():
    """Candidate/accepted level: missing run_key in meta -> blockers."""
    meta = _eligibility_meta()
    meta.pop("run_key", None)
    # run_key missing
    bundle = _bundle_with_meta(meta)
    report = evaluate_eligibility(bundle, "accepted")
    assert not report.passed
    assert any("run_key" in b for b in report.blockers)


def test_evaluate_eligibility_blocks_when_dataset_hash_mode_not_strict():
    """Candidate/accepted: dataset_hash_mode must be STRICT."""
    meta = _eligibility_meta(dataset_hash_mode="FAST_DEV")
    bundle = _bundle_with_meta(meta)
    report = evaluate_eligibility(bundle, "candidate")
    assert not report.passed
    assert any("STRICT" in b or "dataset_hash_mode" in b for b in report.blockers)


def test_evaluate_eligibility_passes_with_full_meta():
    """All required meta (dataset_id_v2, algo, mode, run_key, versions, schema_version) -> passed."""
    meta = _eligibility_meta()
    bundle = _bundle_with_meta(meta)
    for level in ("candidate", "accepted"):
        report = evaluate_eligibility(bundle, level)
        assert report.passed, f"level={level} blockers={report.blockers}"
        assert report.level == level


def test_evaluate_eligibility_blocks_when_rw_enabled_but_rw_adjusted_p_values_missing():
    """Phase 1: when rw_enabled=True, gatekeeper requires rw_adjusted_p_values (blocks if missing)."""
    meta = _eligibility_meta(rw_enabled=True)
    bundle = _bundle_with_meta(meta)
    report = evaluate_eligibility(bundle, "accepted")
    assert not report.passed
    assert any("rw_adjusted_p_values" in b or "rw_enabled" in b for b in report.blockers)


def test_evaluate_eligibility_passes_with_rw_enabled_and_valid_p_values():
    """When rw_enabled=True and rw_adjusted_p_values present and in [0,1], eligibility passes."""
    meta = _eligibility_meta(rw_enabled=True, rw_adjusted_p_values={"s1|1": 0.03, "s2|1": 0.05})
    bundle = _bundle_with_meta(meta)
    report = evaluate_eligibility(bundle, "accepted")
    assert report.passed, report.blockers


def test_evaluate_eligibility_blocks_when_rw_enabled_but_actual_n_sim_zero():
    """When rw_enabled=True and rc_summary has actual_n_sim=0, gatekeeper blocks."""
    meta = _eligibility_meta(rw_enabled=True)
    bundle = _bundle_with_meta(meta)
    rc_summary = {
        "rc_summary_schema_version": RC_SUMMARY_SCHEMA_VERSION,
        "rw_enabled": True,
        "actual_n_sim": 0,
        "hypothesis_ids": ["s1|1"],
    }
    report = evaluate_eligibility(bundle, "accepted", rc_summary=rc_summary)
    assert not report.passed
    assert any("no null simulations" in b.lower() or "actual_n_sim" in b.lower() for b in report.blockers)


def test_evaluate_eligibility_blocks_when_rw_adjusted_p_values_length_mismatch():
    """When rw_enabled and rc_summary has hypothesis_ids, rw_adjusted_p_values length must match."""
    meta = _eligibility_meta(rw_enabled=True, rw_adjusted_p_values={"s1|1": 0.03})
    bundle = _bundle_with_meta(meta)
    rc_summary = {
        "rc_summary_schema_version": RC_SUMMARY_SCHEMA_VERSION,
        "rw_enabled": True,
        "actual_n_sim": 100,
        "hypothesis_ids": ["s1|1", "s2|1"],
    }
    report = evaluate_eligibility(bundle, "accepted", rc_summary=rc_summary)
    assert not report.passed
    assert any("length" in b.lower() or "hypothesis" in b.lower() for b in report.blockers)


def test_evaluate_eligibility_blocks_when_actual_n_sim_below_95_percent_requested():
    """Candidate/accepted: actual_n_sim < 0.95 * requested_n_sim is a blocker (no silent shortfall)."""
    meta = _eligibility_meta(rw_enabled=True, rw_adjusted_p_values={"s1|1": 0.03})
    bundle = _bundle_with_meta(meta)
    rc_summary = {
        "rc_summary_schema_version": RC_SUMMARY_SCHEMA_VERSION,
        "rw_enabled": True,
        "actual_n_sim": 80,
        "requested_n_sim": 100,
        "hypothesis_ids": ["s1|1"],
        "rw_adjusted_p_values": {"s1|1": 0.03},
    }
    report = evaluate_eligibility(bundle, "accepted", rc_summary=rc_summary)
    assert not report.passed
    assert any("95%" in b or "actual_n_sim" in b for b in report.blockers)


def test_evaluate_eligibility_requires_rw_key_order_match_hypothesis_ids():
    """When hypothesis_ids provided, rw_adjusted_p_values key order must equal hypothesis_ids (not just set)."""
    meta = _eligibility_meta(rw_enabled=True, rw_adjusted_p_values={"s2|1": 0.05, "s1|1": 0.03})
    bundle = _bundle_with_meta(meta)
    rc_summary = {
        "rc_summary_schema_version": RC_SUMMARY_SCHEMA_VERSION,
        "rw_enabled": True,
        "actual_n_sim": 100,
        "requested_n_sim": 100,
        "hypothesis_ids": ["s1|1", "s2|1"],
        "rw_adjusted_p_values": {"s2|1": 0.05, "s1|1": 0.03},
    }
    report = evaluate_eligibility(bundle, "accepted", rc_summary=rc_summary)
    assert not report.passed
    assert any("order" in b.lower() for b in report.blockers)
