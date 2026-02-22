"""
Backward-compat import shims: old paths must resolve and refer to same objects as canonical.
No behavior change; purely import resolution and identity checks.
"""

from __future__ import annotations


def test_rng_shim_resolves():
    """crypto_analyzer.rng still resolves and exports seed_root."""
    import crypto_analyzer.rng as rng_mod

    assert hasattr(rng_mod, "seed_root")
    assert callable(rng_mod.seed_root)


def test_rng_seed_root_identical_to_core_seeding():
    """seed_root from rng and from core.seeding are the same callable."""
    from crypto_analyzer.core.seeding import seed_root as seed_root_core
    from crypto_analyzer.rng import seed_root as seed_root_rng

    assert seed_root_rng is seed_root_core


def test_rng_seed_root_same_behavior_sample():
    """Same inputs -> same seed from both import paths."""
    from crypto_analyzer.core.seeding import seed_root as seed_root_core
    from crypto_analyzer.rng import seed_root as seed_root_rng

    run_key = "test_run_key"
    salt = "test_salt"
    s1 = seed_root_rng(run_key, salt=salt)
    s2 = seed_root_core(run_key, salt=salt)
    assert s1 == s2
    assert isinstance(s1, int)
    assert isinstance(s2, int)


def test_core_context_run_context_imports():
    """RunContext and ExecContext import from canonical core.context."""
    from crypto_analyzer.core.context import ExecContext, RunContext

    assert RunContext is not None
    assert ExecContext is not None
    # Smoke: construct once
    rc = RunContext(
        run_key="k",
        run_instance_id="i",
        dataset_id_v2="d",
        engine_version="e",
        config_version="c",
    )
    assert rc.run_key == "k"
    ec = ExecContext(out_dir="/tmp/out")
    assert ec.out_dir == "/tmp/out"
