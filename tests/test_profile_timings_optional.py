"""Profiling: timings.json only when CRYPTO_ANALYZER_PROFILE=1; not in manifest when off."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))


def _fake_returns_and_meta():
    np.random.seed(42)
    n_bars = 60
    n_assets = 3
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


def test_profiling_off_no_timings_file():
    """When CRYPTO_ANALYZER_PROFILE is not set, timings.json is not written."""
    out_dir = Path(__file__).resolve().parent.parent / "tmp_profile_off"
    out_dir.mkdir(parents=True, exist_ok=True)
    timings_path = out_dir / "timings.json"
    if timings_path.exists():
        timings_path.unlink()
    env = os.environ.copy()
    env.pop("CRYPTO_ANALYZER_PROFILE", None)
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

    with patch.dict(os.environ, env, clear=False):
        with patch("crypto_analyzer.research_universe.get_research_assets", return_value=_fake_returns_and_meta()):
            with patch("crypto_analyzer.data.get_factor_returns", return_value=None):
                sys.argv = argv
                from cli import research_report_v2

                research_report_v2.main()
    assert not timings_path.exists(), "timings.json must not be created when profiling is off"


def test_profiling_on_timings_written():
    """When CRYPTO_ANALYZER_PROFILE=1, timings.json is written under out_dir."""
    out_dir = Path(__file__).resolve().parent.parent / "tmp_profile_on"
    out_dir.mkdir(parents=True, exist_ok=True)
    timings_path = out_dir / "timings.json"
    if timings_path.exists():
        timings_path.unlink()
    env = os.environ.copy()
    env["CRYPTO_ANALYZER_PROFILE"] = "1"
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

    with patch.dict(os.environ, env, clear=False):
        with patch("crypto_analyzer.research_universe.get_research_assets", return_value=_fake_returns_and_meta()):
            with patch("crypto_analyzer.data.get_factor_returns", return_value=None):
                sys.argv = argv
                from cli import research_report_v2

                research_report_v2.main()
    assert timings_path.is_file(), "timings.json must be written when CRYPTO_ANALYZER_PROFILE=1"
    import json

    data = json.loads(timings_path.read_text(encoding="utf-8"))
    assert "stages" in data
    assert "run_id" in data
