"""Promotion gating: evaluate_candidate deterministic; require_regime_robustness toggles regime rule."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.promotion import ThresholdConfig, evaluate_candidate
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
    rc_summary = {"rc_p_value": 0.10}
    decision = evaluate_candidate(bundle, cfg, regime_summary_df=None, rc_summary=rc_summary)
    assert decision.status == "rejected"
    assert any("rc_p_value" in r for r in decision.reasons)


def test_require_reality_check_accepts_when_rc_p_value_below_threshold():
    """When require_reality_check=True and rc_p_value <= threshold, no RC reason."""
    bundle = _minimal_bundle(mean_ic=0.03, t_stat=3.0)
    cfg = ThresholdConfig(require_reality_check=True, max_rc_p_value=0.05)
    rc_summary = {"rc_p_value": 0.02}
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
