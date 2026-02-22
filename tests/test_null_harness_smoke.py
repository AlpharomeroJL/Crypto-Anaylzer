"""Null harness: determinism and shape checks; must run in <2s."""

import time

import numpy as np

from crypto_analyzer.stats.null_harness import (
    gen_ar1,
    gen_correlated,
    gen_iid,
    gen_mean_shift,
    run_null_experiment,
)


def test_gen_iid_shape_and_determinism():
    a = gen_iid(50, 3, seed=42)
    b = gen_iid(50, 3, seed=42)
    assert a.shape == (50, 3)
    np.testing.assert_array_almost_equal(a, b)


def test_gen_ar1_shape():
    x = gen_ar1(40, 2, phi=0.5, seed=1)
    assert x.shape == (40, 2)


def test_gen_correlated_shape():
    x = gen_correlated(30, 4, rho=0.3, seed=2)
    assert x.shape == (30, 4)


def test_gen_mean_shift_shape():
    x = gen_mean_shift(20, 2, shift_at=10, delta=0.5, seed=3)
    assert x.shape == (20, 2)


def test_run_null_experiment_determinism():
    def ev(data: np.ndarray) -> float:
        return float(data.mean())

    r1 = run_null_experiment(gen_iid, ev, n_rep=5, seed=10, n=20, k=2)
    r2 = run_null_experiment(gen_iid, ev, n_rep=5, seed=10, n=20, k=2)
    assert r1["n_rep"] == r2["n_rep"] == 5
    v1 = [x.get("value", x) for x in r1["results"]]
    v2 = [x.get("value", x) for x in r2["results"]]
    np.testing.assert_array_almost_equal(v1, v2)


def test_null_harness_runtime_under_two_seconds():
    def ev(data: np.ndarray) -> float:
        return float(data.mean())

    t0 = time.perf_counter()
    run_null_experiment(gen_iid, ev, n_rep=30, seed=0, n=100, k=5)
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0
