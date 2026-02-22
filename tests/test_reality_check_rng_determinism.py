"""Same run_key yields same rc_p_value and null_max_distribution when inputs equal."""

import numpy as np
import pandas as pd

from crypto_analyzer.stats.reality_check import (
    RealityCheckConfig,
    make_null_generator_stationary,
    run_reality_check,
)


def _make_ic_series(n: int, seed: int) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(rng.standard_normal(n).cumsum() * 0.01)


def test_same_run_key_same_rc_p_value_and_null_max():
    n_obs = 100
    series_by_hyp = {
        "a|1": _make_ic_series(n_obs, 1),
        "b|1": _make_ic_series(n_obs, 2),
    }
    observed = pd.Series({"a|1": 0.02, "b|1": 0.01})
    cfg = RealityCheckConfig(
        n_sim=30,
        method="stationary",
        avg_block_length=8,
        seed=42,
        run_key="test-run-key-1",
    )
    null_gen = make_null_generator_stationary(series_by_hyp, cfg)
    res1 = run_reality_check(observed, null_gen, cfg)
    null_gen2 = make_null_generator_stationary(series_by_hyp, cfg)
    res2 = run_reality_check(observed, null_gen2, cfg)
    assert res1["rc_p_value"] == res2["rc_p_value"]
    np.testing.assert_array_almost_equal(res1["null_max_distribution"], res2["null_max_distribution"])
    assert res1.get("seed_root") is not None
    from crypto_analyzer.rng import SALT_RC_NULL, SEED_ROOT_VERSION

    assert res1.get("component_salt") == SALT_RC_NULL
    assert res1.get("seed_version") == SEED_ROOT_VERSION
    spec = res1.get("null_construction_spec")
    assert (
        spec is not None and spec.get("seed_derivation") == "run_key" and spec.get("seed_version") == SEED_ROOT_VERSION
    )


def test_same_seed_no_run_key_reproducible():
    n_obs = 80
    series_by_hyp = {
        "x|1": _make_ic_series(n_obs, 10),
        "y|1": _make_ic_series(n_obs, 11),
    }
    observed = pd.Series({"x|1": 0.015, "y|1": 0.008})
    cfg = RealityCheckConfig(n_sim=25, method="block_fixed", block_size=10, seed=7)
    null_gen = make_null_generator_stationary(series_by_hyp, cfg)
    res1 = run_reality_check(observed, null_gen, cfg)
    null_gen2 = make_null_generator_stationary(series_by_hyp, cfg)
    res2 = run_reality_check(observed, null_gen2, cfg)
    assert res1["rc_p_value"] == res2["rc_p_value"]
    np.testing.assert_array_almost_equal(res1["null_max_distribution"], res2["null_max_distribution"])


def test_different_run_key_different_null_max():
    n_obs = 60
    series_by_hyp = {
        "a|1": _make_ic_series(n_obs, 3),
    }
    observed = pd.Series({"a|1": 0.01})
    cfg1 = RealityCheckConfig(n_sim=20, seed=42, run_key="key-A")
    cfg2 = RealityCheckConfig(n_sim=20, seed=42, run_key="key-B")
    null1 = make_null_generator_stationary(series_by_hyp, cfg1)
    null2 = make_null_generator_stationary(series_by_hyp, cfg2)
    res1 = run_reality_check(observed, null1, cfg1)
    res2 = run_reality_check(observed, null2, cfg2)
    assert not np.allclose(res1["null_max_distribution"], res2["null_max_distribution"])
