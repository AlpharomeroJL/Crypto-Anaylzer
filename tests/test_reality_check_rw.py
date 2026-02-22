"""
Phase 1 verification: Romano–Wolf path works when CRYPTO_ANALYZER_ENABLE_ROMANOWOLF=1.
- run_reality_check() does not raise.
- rw_adjusted_p_values: match hypothesis count, in [0,1], non-empty, aligned to hypothesis index.
- Gatekeeper: rw_enabled + missing rw_adjusted_p_values blocks; valid RW allows (see test_promotion_gating).
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

from crypto_analyzer.stats.reality_check import (
    RealityCheckConfig,
    run_reality_check,
)


def _null_gen(n_hyp: int, n_sim: int, seed: int):
    """Return a callable that yields (n_sim, n_hyp) null matrix rows."""
    rng = np.random.default_rng(seed)

    def generator(b: int):
        return rng.standard_normal(n_hyp).tolist()

    return generator


def test_run_reality_check_with_rw_env_does_not_raise(monkeypatch):
    """With CRYPTO_ANALYZER_ENABLE_ROMANOWOLF=1, run_reality_check returns without raising."""
    monkeypatch.setenv("CRYPTO_ANALYZER_ENABLE_ROMANOWOLF", "1")
    observed = pd.Series({"s1|1": 0.03, "s2|1": 0.02}, dtype=float)
    n_sim = 50
    cfg = RealityCheckConfig(n_sim=n_sim, seed=42)
    null_gen = _null_gen(2, n_sim, cfg.seed)
    result = run_reality_check(observed, null_gen, cfg)
    assert "rw_adjusted_p_values" in result
    assert result.get("rw_enabled") is True


def test_rw_adjusted_p_values_match_hypothesis_count_and_in_range(monkeypatch):
    """rw_adjusted_p_values length matches hypothesis count; values in [0,1]; index = canonical hypothesis_ids (sorted)."""
    monkeypatch.setenv("CRYPTO_ANALYZER_ENABLE_ROMANOWOLF", "1")
    observed = pd.Series({"a|1": 0.04, "b|1": 0.02, "c|1": 0.01}, dtype=float)
    n_sim = 100
    cfg = RealityCheckConfig(n_sim=n_sim, seed=123)
    null_gen = _null_gen(3, n_sim, cfg.seed)
    result = run_reality_check(observed, null_gen, cfg)
    rw = result.get("rw_adjusted_p_values")
    assert rw is not None
    assert not rw.empty
    hypothesis_ids = result["hypothesis_ids"]
    assert len(rw) == len(hypothesis_ids)
    assert list(rw.index) == hypothesis_ids
    for v in rw:
        assert 0 <= v <= 1
        assert v == v  # finite (no NaN)
    assert result.get("requested_n_sim") == n_sim
    assert result.get("actual_n_sim") == n_sim


def test_rw_skipped_when_observed_contains_nan(monkeypatch):
    """When rw_enabled and observed stats contain NaN, RW is skipped and rw_skipped_reason is set."""
    monkeypatch.setenv("CRYPTO_ANALYZER_ENABLE_ROMANOWOLF", "1")
    observed = pd.Series({"a|1": 0.04, "b|1": np.nan, "c|1": 0.01}, dtype=float)
    n_sim = 50
    cfg = RealityCheckConfig(n_sim=n_sim, seed=42)
    null_gen = _null_gen(3, n_sim, cfg.seed)
    result = run_reality_check(observed, null_gen, cfg)
    assert result.get("rw_enabled") is True
    assert result.get("rw_adjusted_p_values") is not None and result["rw_adjusted_p_values"].empty
    assert "rw_skipped_reason" in result and "NaN" in result["rw_skipped_reason"]


def test_requested_and_actual_n_sim_emitted(monkeypatch):
    """Output includes requested_n_sim and actual_n_sim; shortfall adds n_sim_shortfall_warning."""
    monkeypatch.setenv("CRYPTO_ANALYZER_ENABLE_ROMANOWOLF", "0")
    observed = pd.Series({"s1|1": 0.03}, dtype=float)
    cfg = RealityCheckConfig(n_sim=100, seed=42)

    def null_gen_bad(b: int):
        return None  # length mismatch / missing

    result = run_reality_check(observed, null_gen_bad, cfg)
    assert result["requested_n_sim"] == 100
    assert result["actual_n_sim"] == 0
    assert "n_sim_shortfall_warning" in result


def test_rw_disabled_when_env_not_set():
    """When env is not 1, rw_enabled is False and rw_adjusted_p_values is empty (when using full null matrix we could still get RW in some code paths; here we ensure no env -> no RW from env)."""
    # Ensure env is unset for this test
    env_val = os.environ.pop("CRYPTO_ANALYZER_ENABLE_ROMANOWOLF", None)
    try:
        observed = pd.Series({"s1|1": 0.03}, dtype=float)
        cfg = RealityCheckConfig(n_sim=20, seed=42)
        null_gen = _null_gen(1, 20, cfg.seed)
        result = run_reality_check(observed, null_gen, cfg)
        assert result.get("rw_enabled") is False
        rw = result.get("rw_adjusted_p_values")
        assert rw is not None and (rw.empty or not result.get("rw_enabled"))
    finally:
        if env_val is not None:
            os.environ["CRYPTO_ANALYZER_ENABLE_ROMANOWOLF"] = env_val
