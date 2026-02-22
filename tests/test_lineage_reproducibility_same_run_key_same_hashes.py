"""Phase 3 A4: Same run_key and config yields same artifact hashes (reproducibility)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from crypto_analyzer.pipelines.research_pipeline import run_research_pipeline


def test_same_run_key_same_hashes():
    config = {
        "out_dir": "artifacts/research",
        "dataset_id": "demo",
        "signal_name": "momentum_24h",
        "freq": "1h",
        "horizons": [1, 4],
        "seed": 42,
        "n_bars": 80,
        "n_assets": 3,
        "run_key": "fixed_run_key_123",
        "engine_version": "v1",
        "config_version": "c1",
    }
    with tempfile.TemporaryDirectory() as tmp:
        out1 = Path(tmp) / "out1"
        out2 = Path(tmp) / "out2"
        out1.mkdir()
        out2.mkdir()
        c1 = {**config, "out_dir": str(out1)}
        c2 = {**config, "out_dir": str(out2)}
        r1 = run_research_pipeline(c1, hypothesis_id="h1", family_id="f1")
        r2 = run_research_pipeline(c2, hypothesis_id="h1", family_id="f1")
        assert r1.artifact_paths and r2.artifact_paths
        from crypto_analyzer.artifacts import compute_file_sha256

        for key in ("manifest", "metrics_ic", "hashes"):
            if key not in r1.artifact_paths or key not in r2.artifact_paths:
                continue
            h1 = compute_file_sha256(Path(r1.artifact_paths[key]))
            h2 = compute_file_sha256(Path(r2.artifact_paths[key]))
            assert h1 == h2, f"same run_key should yield same hash for {key}"
