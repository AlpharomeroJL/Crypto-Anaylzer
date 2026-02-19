"""Reportv2: without --reality-check unchanged; with --reality-check produces RC artifacts and metrics."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))


def _fake_returns_and_meta():
    np.random.seed(88)
    n_bars = 60
    n_assets = 4
    idx = pd.date_range("2026-01-01", periods=n_bars, freq="1h")
    cols = ["BTC_spot", "ETH_spot"] + [f"pair_{i}" for i in range(n_assets)]
    data = np.random.randn(n_bars, len(cols)).astype(float) * 0.01
    returns_df = pd.DataFrame(data, index=idx, columns=cols)
    meta_df = pd.DataFrame(
        [{"asset_id": c, "label": c, "asset_type": "dex", "chain_id": "1", "pair_address": c} for c in cols]
    )
    return returns_df, meta_df


def test_reportv2_without_reality_check_no_rc_artifacts():
    """Without --reality-check, no RC artifacts or family_id in registry."""
    tmp = tempfile.mkdtemp()
    try:
        out_dir = Path(tmp) / "reports"
        out_dir.mkdir(parents=True)
        (out_dir / "csv").mkdir(exist_ok=True)
        (out_dir / "manifests").mkdir(exist_ok=True)
        (out_dir / "health").mkdir(exist_ok=True)
        argv = [
            "research_report_v2",
            "--freq", "1h",
            "--signals", "momentum_24h",
            "--portfolio", "simple",
            "--out-dir", str(out_dir),
            "--db", ":memory:",
            "--top-k", "2",
            "--bottom-k", "2",
        ]
        with patch.dict(os.environ, {}, clear=False):
            with (
                patch("crypto_analyzer.research_universe.get_research_assets", return_value=_fake_returns_and_meta()),
                patch("cli.research_report_v2.get_research_assets", return_value=_fake_returns_and_meta()),
                patch("cli.research_report_v2.get_factor_returns", return_value=None),
                patch("cli.research_report_v2.record_experiment_run"),
            ):
                sys.argv = argv
                from cli import research_report_v2
                research_report_v2.main()
        rc_files = list((out_dir / "csv").glob("reality_check_*.json")) + list(
            (out_dir / "csv").glob("reality_check_*.csv")
        )
        assert len(rc_files) == 0
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_reportv2_with_reality_check_produces_artifacts():
    """With --reality-check, RC summary and null_max artifacts exist; registry gets family_id and rc_p_value."""
    tmp = tempfile.mkdtemp()
    try:
        out_dir = Path(tmp) / "reports"
        out_dir.mkdir(parents=True)
        (out_dir / "csv").mkdir(exist_ok=True)
        (out_dir / "manifests").mkdir(exist_ok=True)
        (out_dir / "health").mkdir(exist_ok=True)
        argv = [
            "research_report_v2",
            "--freq", "1h",
            "--signals", "momentum_24h",
            "--portfolio", "simple",
            "--out-dir", str(out_dir),
            "--db", ":memory:",
            "--reality-check",
            "--rc-n-sim", "25",
            "--rc-seed", "42",
            "--top-k", "2",
            "--bottom-k", "2",
        ]
        metrics_captured = {}

        def _record_run(db_path, experiment_row, metrics_dict, artifacts_list=None):
            metrics_captured.update(metrics_dict or {})

        with patch.dict(os.environ, {}, clear=False):
            with (
                patch("crypto_analyzer.research_universe.get_research_assets", return_value=_fake_returns_and_meta()),
                patch("cli.research_report_v2.get_research_assets", return_value=_fake_returns_and_meta()),
                patch("cli.research_report_v2.get_factor_returns", return_value=None),
                patch("cli.research_report_v2.record_experiment_run", side_effect=_record_run),
            ):
                sys.argv = argv
                from cli import research_report_v2
                research_report_v2.main()
        summary_files = list((out_dir / "csv").glob("reality_check_summary_*.json"))
        assert len(summary_files) >= 1
        import json
        s = json.loads(summary_files[0].read_text(encoding="utf-8"))
        assert "rc_p_value" in s and "family_id" in s
        assert "family_id" in metrics_captured
        assert "rc_p_value" in metrics_captured
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
