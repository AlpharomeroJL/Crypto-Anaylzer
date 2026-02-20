"""Smoke test: research pipeline runs end-to-end and produces deterministic artifact bundle."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

import pytest

from crypto_analyzer.pipelines.research_pipeline import ResearchPipelineResult, run_research_pipeline


@pytest.fixture
def pipeline_config(tmp_path):
    """Minimal config with synthetic data and temp out_dir."""
    return {
        "out_dir": str(tmp_path / "bundles"),
        "dataset_id": "demo",
        "signal_name": "momentum_24h",
        "freq": "1h",
        "horizons": [1, 4],
        "seed": 42,
        "n_bars": 80,
        "n_assets": 3,
    }


def test_research_pipeline_runs_end_to_end(pipeline_config):
    """Pipeline runs with small synthetic dataset and produces promotion decision + artifact bundle."""
    result = run_research_pipeline(
        pipeline_config,
        hypothesis_id="hyp_demo001",
        family_id="rcfam_demo001",
    )
    assert isinstance(result, ResearchPipelineResult)
    assert result.run_id
    assert result.hypothesis_id == "hyp_demo001"
    assert result.family_id == "rcfam_demo001"
    assert result.decision.status in ("exploratory", "candidate", "accepted", "rejected")
    assert result.bundle_dir
    assert Path(result.bundle_dir).is_dir()


def test_bundle_contains_manifest_metrics_hashes(pipeline_config):
    """Bundle directory contains manifest, at least one metrics file, and hashes file."""
    result = run_research_pipeline(
        pipeline_config,
        hypothesis_id="hyp_demo002",
        family_id="rcfam_demo002",
    )
    bundle_dir = Path(result.bundle_dir)
    manifest_path = bundle_dir / "manifest.json"
    metrics_path = bundle_dir / "metrics_ic.json"
    hashes_path = bundle_dir / "hashes.json"

    assert manifest_path.is_file(), "manifest.json missing"
    assert metrics_path.is_file(), "metrics_ic.json missing"
    assert hashes_path.is_file(), "hashes.json missing"

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest.get("run_id") == result.run_id
    assert manifest.get("hypothesis_id") == result.hypothesis_id
    assert manifest.get("family_id") == result.family_id
    assert "decision_status" in manifest

    with open(hashes_path, encoding="utf-8") as f:
        hashes = json.load(f)
    assert "manifest.json" in hashes
    assert "metrics_ic.json" in hashes
    assert "hashes.json" not in hashes  # hashes file does not hash itself


def test_pipeline_twice_same_inputs_identical_hashes(pipeline_config):
    """Running pipeline twice with same inputs yields identical hashes."""
    result1 = run_research_pipeline(
        pipeline_config,
        hypothesis_id="hyp_same",
        family_id="rcfam_same",
        run_id="fixed_run_001",
    )
    hashes_path1 = Path(result1.bundle_dir) / "hashes.json"
    assert hashes_path1.is_file()
    with open(hashes_path1, encoding="utf-8") as f:
        hashes_first_run = json.load(f)

    result2 = run_research_pipeline(
        pipeline_config,
        hypothesis_id="hyp_same",
        family_id="rcfam_same",
        run_id="fixed_run_001",
    )
    assert result1.run_id == result2.run_id
    assert result1.decision.status == result2.decision.status

    hashes_path2 = Path(result2.bundle_dir) / "hashes.json"
    with open(hashes_path2, encoding="utf-8") as f:
        hashes_second_run = json.load(f)

    assert hashes_first_run == hashes_second_run, "hashes must be identical for same inputs"


def test_pipeline_with_reality_check_produces_rc_artifact(pipeline_config):
    """With enable_reality_check=True, bundle includes rc_summary and meta has rc_p_value."""
    pipeline_config["rc_n_sim"] = 30
    result = run_research_pipeline(
        pipeline_config,
        hypothesis_id="hyp_rc",
        family_id="rcfam_rc",
        enable_reality_check=True,
    )
    bundle_dir = Path(result.bundle_dir)
    rc_path = bundle_dir / "rc_summary.json"
    assert rc_path.is_file()
    with open(rc_path, encoding="utf-8") as f:
        rc = json.load(f)
    assert "rc_p_value" in rc
    assert "hypothesis_ids" in rc
