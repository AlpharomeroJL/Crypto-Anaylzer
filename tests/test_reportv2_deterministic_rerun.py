"""
Deterministic rerun: with CRYPTO_ANALYZER_DETERMINISTIC_TIME set, running reportv2 twice
must produce byte-identical bundle JSON, manifest JSON, and artifact SHA256.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd


def _deterministic_returns_and_meta():
    """Returns (returns_df, meta_df) with fixed seed for reproducible reportv2."""
    np.random.seed(42)
    n_bars = 80
    n_assets = 4
    idx = pd.date_range("2025-01-01", periods=n_bars, freq="1h")
    cols = [f"pair_{i}" for i in range(n_assets)]
    returns_df = pd.DataFrame(
        np.random.randn(n_bars, n_assets).astype(float) * 0.01,
        index=idx,
        columns=cols,
    )
    meta_df = pd.DataFrame(
        [{"asset_id": c, "label": c, "asset_type": "dex", "chain_id": "1", "pair_address": c} for c in cols]
    )
    return returns_df, meta_df


def test_deterministic_rerun_identical_bundle_and_manifest():
    """Run reportv2 twice with CRYPTO_ANALYZER_DETERMINISTIC_TIME; assert byte-identical outputs."""
    import tempfile

    env_val = "2026-01-01T00:00:00Z"
    with patch.dict(os.environ, {"CRYPTO_ANALYZER_DETERMINISTIC_TIME": env_val}, clear=False):
        returns_df, meta_df = _deterministic_returns_and_meta()
        out_dir_1 = Path(__file__).resolve().parent.parent / "tmp_rerun_1"
        out_dir_2 = Path(__file__).resolve().parent.parent / "tmp_rerun_2"
        for d in (out_dir_1, out_dir_2):
            d.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db_path = f.name
        try:
            argv_1 = [
                "research_report_v2",
                "--freq",
                "1h",
                "--signals",
                "momentum_24h",
                "--portfolio",
                "simple",
                "--out-dir",
                str(out_dir_1),
                "--db",
                db_path,
                "--top-k",
                "2",
                "--bottom-k",
                "2",
            ]
            argv_2 = [x.replace(str(out_dir_1), str(out_dir_2)) for x in argv_1]

            def _fake_get_research_assets(db_path: str, freq: str, include_spot: bool = True, **kwargs):
                return _deterministic_returns_and_meta()

            def _fake_get_factor_returns(*args, **kwargs):
                return None

            with (
                patch("crypto_analyzer.cli.reportv2.get_research_assets", side_effect=_fake_get_research_assets),
                patch("crypto_analyzer.cli.reportv2.get_factor_returns", side_effect=_fake_get_factor_returns),
            ):
                # Run 1
                sys.argv = argv_1
                from crypto_analyzer.cli import reportv2

                reportv2.main()
                # Run 2 (same DB so run_key/dataset_id_v2 identical => same seed_root/RC)
                sys.argv = argv_2
                reportv2.main()
        finally:
            try:
                Path(db_path).unlink(missing_ok=True)
            except PermissionError:
                pass
        manifests_1 = list((out_dir_1 / "manifests").glob("*.json"))
        manifests_2 = list((out_dir_2 / "manifests").glob("*.json"))
        assert len(manifests_1) >= 1, "Run 1 should produce at least one manifest"
        assert len(manifests_2) >= 1, "Run 2 should produce at least one manifest"

        # Same run_id => same manifest filename
        run_id_1 = manifests_1[0].stem
        run_id_2 = manifests_2[0].stem
        assert run_id_1 == run_id_2, f"run_id must match: {run_id_1} vs {run_id_2}"

        # Manifest content identical when normalizing output paths (out_dir differs by run)
        import json

        m1 = json.loads(manifests_1[0].read_text())
        m2 = json.loads(manifests_2[0].read_text())

        def _norm_val(v, out1: str, out2: str):
            if isinstance(v, dict):
                return _norm(v, out1, out2)
            if isinstance(v, str):
                return v.replace(out1, "@OUT@").replace(out2, "@OUT@")
            return v

        def _norm(d: dict, out1: str, out2: str) -> dict:
            out = {}
            for k, v in d.items():
                if k == "outputs" and isinstance(v, dict):
                    out[k] = {_norm_val(kk, out1, out2): _norm_val(vv, out1, out2) for kk, vv in v.items()}
                elif isinstance(v, dict):
                    out[k] = _norm(v, out1, out2)
                else:
                    out[k] = _norm_val(v, out1, out2)
            return out

        n1 = _norm(m1, str(out_dir_1), str(out_dir_2))
        n2 = _norm(m2, str(out_dir_1), str(out_dir_2))
        assert n1 == n2, "Manifest (path-normalized) must be identical on rerun"

        # At least one validation bundle
        csv_1 = out_dir_1 / "csv"
        csv_2 = out_dir_2 / "csv"
        bundles_1 = list(csv_1.glob("validation_bundle_*.json")) if csv_1.is_dir() else []
        bundles_2 = list(csv_2.glob("validation_bundle_*.json")) if csv_2.is_dir() else []
        assert len(bundles_1) >= 1, "Run 1 should produce at least one validation bundle"
        assert len(bundles_2) >= 1, "Run 2 should produce at least one validation bundle"

        from crypto_analyzer.artifacts import compute_file_sha256

        for b1 in bundles_1:
            b2 = csv_2 / b1.name
            assert b2.exists(), f"Run 2 should produce same bundle file {b1.name}"
            # Bundle JSON byte-identical (no paths that differ by run)
            assert b1.read_bytes() == b2.read_bytes(), f"Bundle {b1.name} must be byte-identical"
            # Artifact SHA256 must match (file contents identical)
            assert compute_file_sha256(str(b1)) == compute_file_sha256(str(b2)), (
                f"Artifact SHA256 for {b1.name} must match"
            )

    # Cleanup: best-effort remove (ignore locks on DB files on Windows)
    import shutil

    for d in (out_dir_1, out_dir_2):
        if not d.exists():
            continue
        try:
            shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass
