"""Phase 3: case-study liqshock renderer and CLI branch. No DB required."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd

_root = Path(__file__).resolve().parent.parent


def _synthetic_signals_and_metrics():
    """Minimal synthetic data for renderer unit test."""
    idx = pd.date_range("2025-01-01", periods=24, freq="h")
    cols = pd.Index(["pair_a", "pair_b", "pair_c"])
    sig = pd.DataFrame(np.random.randn(24, 3), index=idx, columns=cols)
    signals_dict = {
        "liqshock_N6_w0.01_clip3": sig,
        "liqshock_N6_w0.05_clip3": sig * 0.9,
    }
    orth_dict = dict(signals_dict)
    portfolio_pnls = {
        "liqshock_N6_w0.01_clip3": pd.Series(np.random.randn(24) * 0.01, index=idx),
        "liqshock_N6_w0.05_clip3": pd.Series(np.random.randn(24) * 0.008, index=idx),
    }
    canonical_metrics = {
        "universe_size": 3.0,
        "sharpe": 0.5,
        "sharpe_liqshock_N6_w0.01_clip3": 0.6,
        "sharpe_liqshock_N6_w0.05_clip3": 0.4,
        "p_value_raw_liqshock_N6_w0.01_clip3": 0.02,
        "p_value_raw_liqshock_N6_w0.05_clip3": 0.04,
    }
    returns_df = pd.DataFrame(np.random.randn(24, 3) * 0.01, index=idx, columns=cols)
    return signals_dict, orth_dict, portfolio_pnls, canonical_metrics, returns_df


def test_render_case_study_liqshock_headings_and_tables():
    """Renderer unit test: output contains required headings and both table sections."""
    from crypto_analyzer.cli.case_study_liqshock_renderer import render_case_study_liqshock

    signals_dict, orth_dict, portfolio_pnls, canonical_metrics, returns_df = _synthetic_signals_and_metrics()
    args = MagicMock()
    args.case_study = "liqshock"
    args.freq = "1h"
    args.signals = "liquidity_shock_reversion"
    args.portfolio = "advanced"

    md = render_case_study_liqshock(
        args=args,
        returns_df=returns_df,
        signals_dict=signals_dict,
        orth_dict=orth_dict,
        portfolio_pnls=portfolio_pnls,
        canonical_metrics=canonical_metrics,
        liquidity_panel=None,
        roll_vol_panel=None,
        bars_match_n_ret=3,
        bars_match_n_match=3,
        bars_match_pct=100.0,
        run_id="test_run_id",
        out_dir=Path("/tmp/out"),
        rc_result=None,
        regime_run_id=None,
        regime_coverage_rel_path=None,
    )

    assert "Page 1 — Executive-Level Signal Framing" in md
    assert "False Discoveries Rejected" in md
    assert "Top 10 most valuable pairs" in md
    assert "Research Design Overview" in md
    assert "No forward-looking liquidity measures used" in md
    assert "Execution assumed at t+1 bar" in md
    assert "Parameter grid tested:" in md
    assert "Survived correction:" in md
    assert "Valuable = economically meaningful" in md or "economically meaningful" in md


def test_case_study_liqshock_arg_triggers_renderer():
    """Smoke test: --case-study liqshock produces memo with Page 1 heading (not default report)."""
    import sqlite3
    import tempfile
    from unittest.mock import patch

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        from crypto_analyzer.db.migrations import run_migrations

        run_migrations(conn, db_path)
        conn.close()

        out_dir = _root / "tests" / "out_case_study_smoke"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "csv").mkdir(exist_ok=True)
        (out_dir / "manifests").mkdir(exist_ok=True)
        (out_dir / "health").mkdir(exist_ok=True)

        def _fake_assets(*args, **kwargs):
            idx = pd.date_range("2025-01-01", periods=12, freq="h")
            cols = ["BTC_spot", "ETH_spot", "pair_c"]
            returns_df = pd.DataFrame(np.random.randn(12, 3) * 0.01, index=idx, columns=cols)
            meta_df = pd.DataFrame(
                [{"asset_id": c, "label": c, "asset_type": "dex", "chain_id": "1", "pair_address": c} for c in cols]
            )
            return returns_df, meta_df

        argv = [
            "research_report_v2",
            "--freq",
            "1h",
            "--signals",
            "liquidity_shock_reversion",
            "--portfolio",
            "advanced",
            "--out-dir",
            str(out_dir),
            "--db",
            db_path,
            "--case-study",
            "liqshock",
        ]

        with patch("crypto_analyzer.cli.reportv2.get_research_assets", side_effect=_fake_assets):
            with patch("crypto_analyzer.cli.reportv2.load_bars", return_value=pd.DataFrame()):
                sys.argv = argv
                from crypto_analyzer.cli import reportv2

                code = reportv2.main()

        assert code == 0
        md_files = sorted(out_dir.glob("*.md"))
        assert len(md_files) >= 1
        content = md_files[0].read_text(encoding="utf-8")
        assert "Page 1 — Executive-Level Signal Framing" in content
        assert "False Discoveries Rejected" in content
        assert "Top 10 most valuable pairs" in content
    finally:
        try:
            Path(db_path).unlink(missing_ok=True)
        except PermissionError:
            pass
