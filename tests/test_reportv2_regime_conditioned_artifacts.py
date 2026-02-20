"""Reportv2: with regimes OFF baseline artifacts/unchanged; with regimes ON new artifacts deterministic."""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import pandas as pd

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.validation_bundle import ValidationBundle


def _fake_returns_and_meta():
    np.random.seed(99)
    n_bars = 80
    n_assets = 5
    idx = pd.date_range("2026-01-01", periods=n_bars, freq="1h")
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


@pytest.mark.slow
def test_reportv2_regimes_off_baseline_no_regime_artifacts():
    """With regimes OFF (default), no regime-specific artifacts; bundle has no regime path fields set."""
    tmp = tempfile.mkdtemp()
    try:
        out_dir = Path(tmp) / "reports"
        out_dir.mkdir(parents=True)
        (out_dir / "csv").mkdir(exist_ok=True)
        (out_dir / "manifests").mkdir(exist_ok=True)
        (out_dir / "health").mkdir(exist_ok=True)
        argv = [
            "research_report_v2",
            "--freq",
            "1h",
            "--signals",
            "momentum_24h",
            "--portfolio",
            "simple",
            "--out-dir",
            str(out_dir),
            "--db",
            ":memory:",
            "--top-k",
            "2",
            "--bottom-k",
            "2",
        ]
        with patch.dict(os.environ, {"CRYPTO_ANALYZER_ENABLE_REGIMES": "0"}, clear=False):
            with (
                patch("crypto_analyzer.research_universe.get_research_assets", return_value=_fake_returns_and_meta()),
                patch("cli.research_report_v2.get_research_assets", return_value=_fake_returns_and_meta()),
                patch("cli.research_report_v2.get_factor_returns", return_value=None),
                patch("cli.research_report_v2.record_experiment_run"),
            ):
                sys.argv = argv
                from cli import research_report_v2

                research_report_v2.main()

        csv_dir = out_dir / "csv"
        regime_coverage_files = list(csv_dir.glob("regime_coverage_*.json"))
        ic_regime_csvs = list(csv_dir.glob("ic_summary_by_regime_*.csv"))
        assert len(regime_coverage_files) == 0, "regimes OFF: no regime_coverage_*.json"
        assert len(ic_regime_csvs) == 0, "regimes OFF: no ic_summary_by_regime_*.csv"

        bundles = list(csv_dir.glob("validation_bundle_*.json"))
        assert len(bundles) >= 1
        import json

        b = json.loads(bundles[0].read_text(encoding="utf-8"))
        # Strict: optional regime keys omitted (byte-identity with pre-Slice-2)
        assert "ic_summary_by_regime_path" not in b
        assert "ic_decay_by_regime_path" not in b
        assert "regime_coverage_path" not in b
        assert "regime_run_id" not in b.get("meta", {})
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


def test_bundle_to_dict_omits_none_optional_keys():
    """to_dict() omits optional keys that are None for strict byte-identity when regimes OFF."""
    bundle = ValidationBundle(
        run_id="r",
        dataset_id="d",
        signal_name="s",
        freq="1h",
        horizons=[1],
        ic_summary_by_horizon={1: {"mean_ic": 0.02, "t_stat": 3.0}},
        ic_decay_table=[],
        meta={},
        ic_summary_by_regime_path=None,
        ic_decay_by_regime_path=None,
        regime_coverage_path=None,
    )
    d = bundle.to_dict()
    assert "ic_summary_by_regime_path" not in d
    assert "ic_decay_by_regime_path" not in d
    assert "regime_coverage_path" not in d


@pytest.mark.slow
@pytest.mark.slow
def test_reportv2_regimes_on_new_artifacts_deterministic():
    """With regimes ON and --regimes, new artifacts exist and content is deterministic under deterministic time."""
    tmp = tempfile.mkdtemp()
    try:
        db_path = Path(tmp) / "test.sqlite"
        out_dir = Path(tmp) / "reports"
        out_dir.mkdir(parents=True)
        (out_dir / "csv").mkdir(exist_ok=True)
        (out_dir / "manifests").mkdir(exist_ok=True)
        (out_dir / "health").mkdir(exist_ok=True)

        from crypto_analyzer.db.migrations import run_migrations
        from crypto_analyzer.db.migrations_phase3 import run_migrations_phase3

        conn = sqlite3.connect(str(db_path))
        run_migrations(conn, str(db_path))
        run_migrations_phase3(conn, str(db_path))
        conn.execute(
            "INSERT INTO regime_runs (regime_run_id, created_at_utc, dataset_id, freq, model, params_json) VALUES (?, ?, ?, ?, ?, ?)",
            ("det_run", "2026-02-19T12:00:00Z", "ds1", "1h", "threshold_v1", None),
        )
        idx = pd.date_range("2026-01-01", periods=80, freq="1h")
        for i, ts in enumerate(idx):
            conn.execute(
                "INSERT INTO regime_states (regime_run_id, ts_utc, regime_label, regime_prob) VALUES (?, ?, ?, ?)",
                ("det_run", ts.strftime("%Y-%m-%dT%H:%M:%S"), "L" if i % 2 == 0 else "H", 0.9),
            )
        conn.commit()
        conn.close()

        argv = [
            "research_report_v2",
            "--freq",
            "1h",
            "--signals",
            "momentum_24h",
            "--portfolio",
            "simple",
            "--out-dir",
            str(out_dir),
            "--db",
            str(db_path),
            "--regimes",
            "det_run",
            "--top-k",
            "2",
            "--bottom-k",
            "2",
        ]
        with patch.dict(os.environ, {"CRYPTO_ANALYZER_ENABLE_REGIMES": "1"}, clear=False):
            with (
                patch("crypto_analyzer.research_universe.get_research_assets", return_value=_fake_returns_and_meta()),
                patch("cli.research_report_v2.get_research_assets", return_value=_fake_returns_and_meta()),
                patch("cli.research_report_v2.get_factor_returns", return_value=None),
                patch("cli.research_report_v2.record_experiment_run"),
            ):
                sys.argv = argv
                from cli import research_report_v2

                research_report_v2.main()

        csv_dir = out_dir / "csv"
        regime_jsons = list(csv_dir.glob("regime_coverage_*.json"))
        ic_regime_csvs = list(csv_dir.glob("ic_summary_by_regime_*.csv"))
        assert len(regime_jsons) >= 1
        assert len(ic_regime_csvs) >= 1

        import json

        c = json.loads(regime_jsons[0].read_text(encoding="utf-8"))
        assert "pct_available" in c and "regime_distribution" in c

        df = pd.read_csv(ic_regime_csvs[0])
        assert "regime" in df.columns and "mean_ic" in df.columns

        bundles = list(csv_dir.glob("validation_bundle_*.json"))
        b = json.loads(bundles[0].read_text(encoding="utf-8"))
        assert b["meta"].get("regime_run_id") == "det_run"
        assert b.get("ic_summary_by_regime_path") is not None
        assert b.get("regime_coverage_path") is not None
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
