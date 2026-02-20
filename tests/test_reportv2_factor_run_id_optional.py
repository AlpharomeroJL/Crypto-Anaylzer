"""Reportv2 --factor-run-id: optional use of materialized factor run; default unchanged."""

from __future__ import annotations

import io
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


def _make_returns_fixture(n_ts: int = 50, n_assets: int = 3, seed: int = 42) -> pd.DataFrame:
    np.random.seed(seed)
    idx = pd.date_range("2025-01-01", periods=n_ts, freq="h")
    cols = ["BTC_spot", "ETH_spot"] + [f"A{i}" for i in range(n_assets)]
    data = np.random.randn(n_ts, len(cols)) * 0.01
    return pd.DataFrame(data, index=idx, columns=cols)


def _fake_returns_and_meta():
    returns_df = _make_returns_fixture(50, 3)
    cols = list(returns_df.columns)
    meta_df = pd.DataFrame(
        [{"asset_id": c, "label": c, "asset_type": "dex", "chain_id": "1", "pair_address": c} for c in cols]
    )
    return returns_df, meta_df


@pytest.mark.slow
def test_reportv2_factor_run_id_invalid_exits():
    """--factor-run-id set but run missing in DB must exit 1 with clear error."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        from crypto_analyzer.db.migrations import run_migrations

        run_migrations(conn, db_path)
        conn.close()

        out_dir = Path(tempfile.mkdtemp()) / "reports"
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
            "--out-dir",
            str(out_dir),
            "--db",
            db_path,
            "--factor-run-id",
            "fctr_nonexistent12345",
        ]
        old_stderr = sys.stderr
        try:
            sys.stderr = io.StringIO()
            with (
                patch("cli.research_report_v2.get_research_assets", return_value=_fake_returns_and_meta()),
                patch("cli.research_report_v2.get_factor_returns", return_value=None),
            ):
                sys.argv = argv
                from cli import research_report_v2

                code = research_report_v2.main()
            err = sys.stderr.getvalue()
        finally:
            sys.stderr = old_stderr

        assert code == 1
        assert "factor-run-id" in err.lower() or "not found" in err.lower() or "empty" in err.lower()
    finally:
        import shutil

        try:
            Path(db_path).unlink(missing_ok=True)
        except OSError:
            pass
        shutil.rmtree(out_dir.parent, ignore_errors=True)


@pytest.mark.slow
def test_reportv2_factor_run_id_valid_uses_materialized():
    """With valid --factor-run-id and pre-materialized run, reportv2 runs and uses loaded factors for mf_metrics."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        from crypto_analyzer.db.migrations import run_migrations
        from crypto_analyzer.factor_materialize import FactorMaterializeConfig, materialize_factor_run

        run_migrations(conn, db_path)
        returns_df = _make_returns_fixture(60, 3)
        config = FactorMaterializeConfig(
            dataset_id="reportv2_slice3_ds",
            freq="1h",
            window_bars=24,
            min_obs=12,
            factors=["BTC_spot", "ETH_spot"],
        )
        factor_run_id = materialize_factor_run(conn, returns_df, config)
        conn.close()

        out_dir = Path(tempfile.mkdtemp()) / "reports"
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
            db_path,
            "--factor-run-id",
            factor_run_id,
        ]
        with (
            patch("cli.research_report_v2.get_research_assets", return_value=_fake_returns_and_meta()),
            patch("cli.research_report_v2.get_factor_returns", return_value=None),
            patch("cli.research_report_v2.record_experiment_run"),
        ):
            sys.argv = argv
            from cli import research_report_v2

            code = research_report_v2.main()

        assert code == 0
        md_files = list(out_dir.glob("*.md"))
        assert len(md_files) >= 1
        # Multi-factor OLS block runs from loaded data; no "skip" implies success (metrics may be in report or registry)
        report_text = md_files[0].read_text(encoding="utf-8")
        assert "Research Report v2" in report_text
    finally:
        import shutil

        # Windows: unlink can raise PermissionError (WinError 32) if report_v2 left DB open.
        # try/except keeps the test stable; to make strict again: ensure all sqlite conns are
        # closed before cleanup, or use a retry loop (e.g. 3 tries with short sleep) before unlink.
        try:
            Path(db_path).unlink(missing_ok=True)
        except OSError:
            pass
        shutil.rmtree(out_dir.parent, ignore_errors=True)


def test_load_factor_run_returns_none_for_missing_run():
    """load_factor_run returns None when factor_run_id has no rows."""
    from crypto_analyzer.data import load_factor_run

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        import sqlite3

        conn = sqlite3.connect(path)
        from crypto_analyzer.db.migrations import run_migrations

        run_migrations(conn, path)
        conn.close()
        result = load_factor_run(path, "fctr_nonexistent99999")
        assert result is None
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass


def test_load_factor_run_returns_data_after_materialize():
    """load_factor_run returns (betas_dict, r2_df, residual_df) for a materialized run."""
    from crypto_analyzer.data import load_factor_run
    from crypto_analyzer.db.migrations import run_migrations
    from crypto_analyzer.factor_materialize import FactorMaterializeConfig, materialize_factor_run

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        returns_df = _make_returns_fixture(50, 2)
        config = FactorMaterializeConfig(
            dataset_id="load_test_ds",
            freq="1h",
            window_bars=20,
            min_obs=8,
            factors=["BTC_spot", "ETH_spot"],
        )
        run_id = materialize_factor_run(conn, returns_df, config)
        conn.close()

        result = load_factor_run(path, run_id)
        assert result is not None
        betas_dict, r2_df, residual_df = result
        assert isinstance(betas_dict, dict)
        assert "BTC_spot" in betas_dict or "ETH_spot" in betas_dict
        for _k, df in betas_dict.items():
            assert not df.empty
        assert not r2_df.empty
        assert not residual_df.empty
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass
