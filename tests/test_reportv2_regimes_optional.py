"""Reportv2 --regimes: optional; no change when regimes disabled; extra artifacts when enabled."""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))


def _fake_returns_and_meta():
    np.random.seed(123)
    n_bars = 60
    n_assets = 4
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
def test_reportv2_without_regimes_flag_has_no_regime_section():
    """With regimes disabled (default), report does not contain Regime-conditioned section."""
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
        md_files = list(out_dir.glob("*.md"))
        assert len(md_files) >= 1
        report_text = md_files[0].read_text(encoding="utf-8")
        # Phase 3 optional section (regime_run_id) must not appear when regimes disabled
        assert "Regime-conditioned IC summary" not in report_text
        assert "Regime run: `" not in report_text
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.slow
def test_reportv2_regimes_set_but_flag_off_fails_fast():
    """--regimes set but CRYPTO_ANALYZER_ENABLE_REGIMES=0 must exit 1 with clear error (no silent ignore)."""
    import io

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
            "--regimes",
            "rgm_any",
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
            ):
                sys.argv = argv
                from cli import research_report_v2

                err = io.StringIO()
                with patch("sys.stderr", err):
                    exit_code = research_report_v2.main()
        assert exit_code == 1
        assert "CRYPTO_ANALYZER_ENABLE_REGIMES" in err.getvalue()
        assert "disabled" in err.getvalue().lower() or "regimes" in err.getvalue().lower()
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.slow
@pytest.mark.slow
def test_reportv2_with_regimes_enabled_and_run_id_emits_regime_artifacts():
    """With ENABLE_REGIMES=1 and --regimes <id>, regime section and regime_summary artifacts appear."""
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
            ("rgm_test_123", "2026-02-19T12:00:00Z", "ds1", "1h", "threshold_vol_v1", None),
        )
        # Align regime_states to mock returns index: 60 bars from 2026-01-01 at 1h
        idx = pd.date_range("2026-01-01", periods=60, freq="1h")
        for i, ts in enumerate(idx):
            ts_str = ts.strftime("%Y-%m-%dT%H:%M:%S")
            conn.execute(
                "INSERT INTO regime_states (regime_run_id, ts_utc, regime_label, regime_prob) VALUES (?, ?, ?, ?)",
                ("rgm_test_123", ts_str, "low_vol" if i % 2 == 0 else "med_vol", 0.9),
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
            "rgm_test_123",
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

        md_files = list(out_dir.glob("*.md"))
        assert len(md_files) >= 1
        # Slice 2: per-signal regime artifacts (ic_summary_by_regime_*, ic_decay_by_regime_*, regime_coverage_*.json)
        regime_csvs = list((out_dir / "csv").glob("ic_summary_by_regime_*.csv"))
        regime_jsons = list((out_dir / "csv").glob("regime_coverage_*.json"))
        assert len(regime_csvs) >= 1 or len(regime_jsons) >= 1, (
            "expected ic_summary_by_regime CSV or regime_coverage JSON when ENABLE_REGIMES=1 and --regimes set"
        )
        report_text = md_files[0].read_text(encoding="utf-8")
        assert "Regime-conditioned summary" in report_text
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
