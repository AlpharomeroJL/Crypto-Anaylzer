"""
Phase 3.5 A2: RunContext and ExecContext plumbing — pipeline and reportv2 can construct and pass context.
Candidate/accepted path rejects missing context fields early.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from crypto_analyzer.core.context import ExecContext, RunContext
from crypto_analyzer.pipelines.research_pipeline import run_research_pipeline


def test_pipeline_constructs_run_context_from_config():
    """Pipeline builds RunContext from config when run_context not provided."""
    config = {
        "out_dir": "artifacts/research",
        "dataset_id": "demo",
        "run_key": "rk_smoke",
        "dataset_id_v2": "ds_v2_smoke",
        "engine_version": "v1",
        "config_version": "c1",
        "seed_version": 1,
    }
    result = run_research_pipeline(config, "hyp_smoke", "fam_smoke")
    assert result.run_id
    assert result.bundle_dir


def test_pipeline_accepts_explicit_run_context():
    """Pipeline uses provided RunContext for lineage/RC identity."""
    run_ctx = RunContext(
        run_key="rk_explicit",
        run_instance_id="run_explicit",
        dataset_id_v2="ds_v2_explicit",
        engine_version="ev1",
        config_version="cv1",
        seed_version=1,
    )
    config = {"out_dir": "artifacts/research", "dataset_id": "demo"}
    result = run_research_pipeline(
        config,
        "hyp_explicit",
        "fam_explicit",
        run_id="run_explicit",
        run_context=run_ctx,
    )
    assert result.run_id == "run_explicit"


def test_run_context_require_for_promotion_rejects_missing_run_key():
    """RunContext.require_for_promotion() raises when run_key missing."""
    ctx = RunContext(
        run_key="",
        run_instance_id="r1",
        dataset_id_v2="ds1",
        engine_version="v1",
        config_version="c1",
    )
    with pytest.raises(ValueError, match="run_key"):
        ctx.require_for_promotion()


def test_run_context_require_for_promotion_rejects_missing_dataset_id_v2():
    """RunContext.require_for_promotion() raises when dataset_id_v2 missing."""
    ctx = RunContext(
        run_key="rk1",
        run_instance_id="r1",
        dataset_id_v2="",
        engine_version="v1",
        config_version="c1",
    )
    with pytest.raises(ValueError, match="dataset_id_v2"):
        ctx.require_for_promotion()


def test_run_context_require_for_promotion_rejects_missing_engine_version():
    """RunContext.require_for_promotion() raises when engine_version missing."""
    ctx = RunContext(
        run_key="rk1",
        run_instance_id="r1",
        dataset_id_v2="ds1",
        engine_version="",
        config_version="c1",
    )
    with pytest.raises(ValueError, match="engine_version"):
        ctx.require_for_promotion()


def test_run_context_require_for_promotion_rejects_missing_config_version():
    """RunContext.require_for_promotion() raises when config_version is None or empty."""
    ctx = RunContext(
        run_key="rk1",
        run_instance_id="r1",
        dataset_id_v2="ds1",
        engine_version="v1",
        config_version=None,  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="config_version"):
        ctx.require_for_promotion()
    ctx_empty = RunContext(
        run_key="rk1",
        run_instance_id="r1",
        dataset_id_v2="ds1",
        engine_version="v1",
        config_version="",
    )
    with pytest.raises(ValueError, match="config_version"):
        ctx_empty.require_for_promotion()


def test_run_context_require_for_promotion_passes_when_complete():
    """RunContext.require_for_promotion() does not raise when all required fields set."""
    ctx = RunContext(
        run_key="rk1",
        run_instance_id="r1",
        dataset_id_v2="ds1",
        engine_version="v1",
        config_version="c1",
    )
    ctx.require_for_promotion()


def test_exec_context_construction():
    """ExecContext can be constructed with out_dir and optional backend/db_path."""
    ec = ExecContext(out_dir=Path("out"), backend="sqlite", db_path="/tmp/db.sqlite")
    assert ec.out_dir == Path("out")
    assert ec.backend == "sqlite"
    assert ec.db_path == "/tmp/db.sqlite"
    assert ec.deterministic_time is True
