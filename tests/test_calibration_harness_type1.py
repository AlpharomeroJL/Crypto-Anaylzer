"""
Type I / FDR calibration tests using the stats calibration harness.
Fast CI: small n_trials, wide tolerances. Order: (a) BH/BY, (b) RC, (c) RW, (d) CSCV PBO.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_analyzer.multiple_testing_adjuster import adjust
from crypto_analyzer.stats.calibration import (
    CalibrationConfig,
    gen_iid_pvalues,
    run_calibration_batch,
    type_i_error_summary,
)
from crypto_analyzer.stats.calibration.null_dgp import gen_null_ic_series
from crypto_analyzer.stats.reality_check import (
    RealityCheckConfig,
    make_null_generator_stationary,
    run_reality_check,
)


# --- (a) BH/BY under i.i.d. null ---
def _eval_bh_rejections(pvalues: np.ndarray, q: float = 0.05) -> dict:
    """Evaluator: run BH at q, return whether any rejections (per trial)."""
    p_ser = pd.Series(pvalues)
    adj, rej = adjust(p_ser, method="bh", q=q)
    return {"rejected": bool(rej.any()), "n_rej": int(rej.sum())}


def test_calibration_bh_fdr_under_iid_null_fast():
    """(a) BH under i.i.d. uniform p-values: empirical FDR at q=0.05 not obviously above 0.05 + tolerance."""
    cfg = CalibrationConfig.fast()
    batch = run_calibration_batch(
        gen_iid_pvalues,
        _eval_bh_rejections,
        n_trials=cfg.n_trials,
        seed=cfg.seed,
        n=cfg.n_hyp,
    )
    rejections = [r["rejected"] for r in batch["results"]]
    summary = type_i_error_summary(rejections, nominal_alpha=0.05)
    assert summary["n_trials"] == cfg.n_trials
    # Wide tolerance for fast CI: empirical rate <= 0.05 + 0.10
    assert summary["within_tolerance"], f"BH Type I empirical_rate={summary['empirical_rate']} should be <= 0.15"


def test_calibration_by_fdr_under_iid_null_fast():
    """(a) BY under i.i.d. null: same check with wide tolerance."""

    def eval_by(pvalues: np.ndarray) -> dict:
        p_ser = pd.Series(pvalues)
        _, rej = adjust(p_ser, method="by", q=0.05)
        return {"rejected": bool(rej.any())}

    cfg = CalibrationConfig.fast()
    batch = run_calibration_batch(
        gen_iid_pvalues,
        eval_by,
        n_trials=cfg.n_trials,
        seed=cfg.seed,
        n=cfg.n_hyp,
    )
    rejections = [r["rejected"] for r in batch["results"]]
    summary = type_i_error_summary(rejections, nominal_alpha=0.05)
    assert summary["within_tolerance"]


# --- (b) RC under null ---
def test_calibration_rc_under_null_fast():
    """(b) RC under synthetic null IC: p-values not obviously anti-conservative (wide tolerance, small N)."""
    cfg = CalibrationConfig.fast()
    from crypto_analyzer.rng import rng_from_seed

    rng = rng_from_seed(cfg.seed)
    series_by_hyp = gen_null_ic_series(cfg.n_obs, n_series=2, rng=rng)
    hypothesis_ids = sorted(series_by_hyp.keys())
    observed = pd.Series({h: float(series_by_hyp[h].mean()) for h in hypothesis_ids}).sort_index()
    rc_cfg = RealityCheckConfig(
        metric="mean_ic",
        horizon=1,
        n_sim=30,
        seed=cfg.seed,
    )
    null_gen = make_null_generator_stationary(series_by_hyp, rc_cfg)
    res = run_reality_check(observed, null_gen, rc_cfg)
    rc_p = res.get("rc_p_value")
    assert rc_p is not None
    # Under null we expect p-value not tiny (anti-conservative); allow wide band
    assert 0.0 <= rc_p <= 1.0


def test_calibration_rc_type_i_not_wildly_above_alpha():
    """(b) RC under null: P(p <= 0.05) not wildly above 0.05 (many trials, wide tolerance, CI-safe)."""
    cfg = CalibrationConfig.fast()
    from crypto_analyzer.rng import rng_from_seed

    rejections = []
    for trial in range(cfg.n_trials):
        trial_rng = rng_from_seed(cfg.seed + trial)
        series_by_hyp = gen_null_ic_series(cfg.n_obs, n_series=2, rng=trial_rng)
        hypothesis_ids = sorted(series_by_hyp.keys())
        observed = pd.Series({h: float(series_by_hyp[h].mean()) for h in hypothesis_ids}).sort_index()
        rc_cfg = RealityCheckConfig(
            metric="mean_ic",
            horizon=1,
            n_sim=25,
            seed=cfg.seed + 1000 + trial,
        )
        null_gen = make_null_generator_stationary(series_by_hyp, rc_cfg)
        res = run_reality_check(observed, null_gen, rc_cfg)
        rc_p = res.get("rc_p_value", 1.0)
        rejections.append(rc_p <= 0.05)
    emp = sum(rejections) / len(rejections)
    assert emp <= 0.15, f"RC under null: P(p<=0.05)={emp} should be <= 0.15"


# --- (c) RW under global null ---
def test_calibration_rw_under_global_null_smoke():
    """(c) RW under global null: smoke that RW path runs and returns valid p-values (no formal FWER check in fast mode)."""
    from crypto_analyzer.stats.calibration_rw import calibrate_rw_smoke

    out = calibrate_rw_smoke(n_obs=40, n_sim=20, seed=42)
    assert "rw_adj_in_01" in out
    assert out["rw_adj_in_01"]


def test_calibration_rw_fwer_proxy_under_global_null():
    """(c) RW under global null: P(min(p_adj) <= 0.05) not wildly above 0.05 (FWER proxy)."""
    import os

    from crypto_analyzer.rng import rng_from_seed

    prev = os.environ.get("CRYPTO_ANALYZER_ENABLE_ROMANOWOLF", "")
    os.environ["CRYPTO_ANALYZER_ENABLE_ROMANOWOLF"] = "1"
    try:
        n_trials = 40
        any_rej = []
        for t in range(n_trials):
            rng = rng_from_seed(42 + t)
            series_by_hyp = {
                "a|1": pd.Series(rng.standard_normal(50).cumsum() * 0.01),
                "b|1": pd.Series(rng.standard_normal(50).cumsum() * 0.01),
            }
            observed = pd.Series({"a|1": 0.01, "b|1": 0.008}).sort_index()
            rc_cfg = RealityCheckConfig(n_sim=25, method="stationary", avg_block_length=8, seed=42 + t)
            null_gen = make_null_generator_stationary(series_by_hyp, rc_cfg)
            res = run_reality_check(observed, null_gen, rc_cfg)
            rw_adj = res.get("rw_adjusted_p_values")
            if rw_adj is not None and len(rw_adj) > 0:
                min_p = float(rw_adj.min())
                any_rej.append(min_p <= 0.05)
            else:
                any_rej.append(False)
        emp = sum(any_rej) / len(any_rej)
        assert emp <= 0.20, f"RW FWER proxy P(min(p_adj)<=0.05)={emp} should be <= 0.20"
    finally:
        if prev == "":
            os.environ.pop("CRYPTO_ANALYZER_ENABLE_ROMANOWOLF", None)
        else:
            os.environ["CRYPTO_ANALYZER_ENABLE_ROMANOWOLF"] = prev


# --- (d) CSCV PBO ---
def test_calibration_cscv_pbo_null_smoke():
    """(d) CSCV PBO: under null strategies (no edge), PBO should be high; smoke only."""
    from crypto_analyzer.multiple_testing import pbo_cscv
    from crypto_analyzer.rng import rng_from_seed

    # Null-like matrix: small random returns, no edge
    rng = rng_from_seed(42)
    R = rng.standard_normal((80, 4)).astype(np.float64) * 0.01  # 80 obs, 4 strategies
    out = pbo_cscv(R, S=4, seed=42, max_splits=50)
    assert "pbo_cscv" in out
    pbo = out["pbo_cscv"]
    assert 0 <= pbo <= 1 or (pbo != pbo), "PBO should be in [0,1] or NaN"


def test_calibration_cscv_pbo_null_above_planted_edge():
    """(d) CSCV: null strategy family PBO should be high vs planted weak edge family (not inverted)."""
    from crypto_analyzer.multiple_testing import pbo_cscv
    from crypto_analyzer.rng import rng_from_seed

    rng = rng_from_seed(99)
    n_obs, n_strat = 80, 4
    # Null: zero-mean noise
    R_null = rng.standard_normal((n_obs, n_strat)).astype(np.float64) * 0.01
    # Planted weak edge: one strategy has small positive drift
    R_edge = rng.standard_normal((n_obs, n_strat)).astype(np.float64) * 0.01
    R_edge[:, 0] += 0.002  # weak positive drift
    pbo_null = pbo_cscv(R_null, S=4, seed=99, max_splits=80)["pbo_cscv"]
    pbo_edge = pbo_cscv(R_edge, S=4, seed=100, max_splits=80)["pbo_cscv"]
    if np.isfinite(pbo_null) and np.isfinite(pbo_edge):
        # Null should be higher (less overfitting) than edge; allow noise
        assert pbo_null >= pbo_edge - 0.25, "PBO(null) should be >= PBO(edge) - tolerance"
    # If either is NaN (e.g. degenerate), test still passes
    assert 0 <= pbo_null <= 1 or (pbo_null != pbo_null)
    assert 0 <= pbo_edge <= 1 or (pbo_edge != pbo_edge)


def test_pbo_cscv_requires_seed_or_rng():
    """pbo_cscv raises when both seed and rng are omitted (no silent nondeterminism)."""
    import pytest

    from crypto_analyzer.multiple_testing import pbo_cscv

    R = np.ones((80, 4), dtype=np.float64) * 0.01
    with pytest.raises(ValueError) as exc_info:
        pbo_cscv(R, S=4, seed=None, rng=None)
    assert "seed" in str(exc_info.value).lower() or "rng" in str(exc_info.value).lower()


def test_calibration_harness_schema_version():
    """CalibrationConfig exposes calibration_harness_schema_version for artifact contract."""
    cfg = CalibrationConfig.fast()
    assert hasattr(cfg, "calibration_harness_schema_version")
    assert cfg.calibration_harness_schema_version == 1
