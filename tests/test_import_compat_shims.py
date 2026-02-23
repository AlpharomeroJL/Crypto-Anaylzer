"""
Import compatibility and shim identity tests.
Ensures old import paths still work and re-exports are the same objects as canonical.
No behavior change; byte-for-byte determinism preserved.
"""

from __future__ import annotations

import sys


def test_import_crypto_analyzer_rng_works():
    """import crypto_analyzer.rng works (shim)."""
    import crypto_analyzer.rng as rng_mod

    assert rng_mod is not None
    assert hasattr(rng_mod, "seed_root")
    assert hasattr(rng_mod, "rng_for")
    assert hasattr(rng_mod, "rng_from_seed")


def test_seed_root_identity_and_same_output():
    """seed_root from crypto_analyzer.rng and crypto_analyzer.core.seeding are the same callable and produce same output."""
    from crypto_analyzer import rng
    from crypto_analyzer.core import seeding

    assert rng.seed_root is seeding.seed_root
    out_rng = rng.seed_root("run_key_1", salt="test_salt")
    out_canonical = seeding.seed_root("run_key_1", salt="test_salt")
    assert out_rng == out_canonical


def test_run_context_exec_context_import_from_core_context():
    """RunContext and ExecContext import from crypto_analyzer.core.context and crypto_analyzer.core."""
    from crypto_analyzer.core import ExecContext, RunContext, context

    assert RunContext is context.RunContext
    assert ExecContext is context.ExecContext


def test_stable_public_surfaces_import_cleanly():
    """Stable public surfaces import cleanly: data, artifacts, stats, governance."""
    from crypto_analyzer import artifacts, data, governance, stats

    assert hasattr(data, "load_bars")
    assert hasattr(artifacts, "compute_file_sha256")
    assert hasattr(stats, "run_reality_check")
    assert hasattr(governance, "promote")
    assert hasattr(governance, "evaluate_and_record")


def test_pipeline_facade_exports_run_research_pipeline():
    """crypto_analyzer.pipeline exposes run_research_pipeline and ResearchPipelineResult."""
    from crypto_analyzer import pipeline
    from crypto_analyzer.pipelines import research_pipeline as rp_impl

    assert hasattr(pipeline, "run_research_pipeline")
    assert pipeline.run_research_pipeline is rp_impl.run_research_pipeline
    assert pipeline.ResearchPipelineResult is rp_impl.ResearchPipelineResult


def test_facades_do_not_import_cli_or_promotion():
    """Importing core/data/artifacts/stats/rng does not pull in cli or promotion (lightweight boundary smoke)."""
    before = set(sys.modules.keys())
    # Facades that must not depend on cli or promotion (pipeline intentionally re-exports from pipelines, which uses promotion).
    import crypto_analyzer.artifacts  # noqa: F401
    import crypto_analyzer.data  # noqa: F401
    import crypto_analyzer.rng  # noqa: F401
    import crypto_analyzer.stats  # noqa: F401
    from crypto_analyzer import core  # noqa: F401

    after = set(sys.modules.keys())
    new_modules = after - before
    assert "cli" not in new_modules and "crypto_analyzer.cli" not in new_modules, (
        "core/data/artifacts/stats/rng must not import cli"
    )
    assert "crypto_analyzer.promotion" not in new_modules, (
        "core/data/artifacts/stats/rng must not import crypto_analyzer.promotion"
    )
