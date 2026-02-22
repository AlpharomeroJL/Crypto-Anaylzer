"""Tests for governance_seeding: stable seeds and different salt changes output."""

import numpy as np

from crypto_analyzer.governance_seeding import rng_for, seed_for


def test_seed_for_stable_across_calls():
    a = seed_for("rc", "run-1", "")
    b = seed_for("rc", "run-1", "")
    assert a == b
    assert isinstance(a, int)
    assert 0 <= a < 2**63


def test_seed_for_different_salt_different_output():
    s1 = seed_for("rc", "run-1", "a")
    s2 = seed_for("rc", "run-1", "b")
    assert s1 != s2


def test_seed_for_different_component_different_output():
    s1 = seed_for("rc", "run-1", "")
    s2 = seed_for("pbo_cscv", "run-1", "")
    assert s1 != s2


def test_rng_for_same_args_same_sequence():
    r1 = rng_for("test", "key", "salt")
    r2 = rng_for("test", "key", "salt")
    u1 = r1.random(5)
    u2 = r2.random(5)
    np.testing.assert_array_almost_equal(u1, u2)


def test_rng_for_different_salt_different_sequence():
    r1 = rng_for("test", "key", "a")
    r2 = rng_for("test", "key", "b")
    u1 = r1.random(5)
    u2 = r2.random(5)
    assert not np.allclose(u1, u2)
