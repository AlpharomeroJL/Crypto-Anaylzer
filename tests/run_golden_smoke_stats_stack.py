"""
Golden run smoke for stats stack: RW on/off, stats_overview and RC contract.
Run from repo root: python tests/run_golden_smoke_stats_stack.py
Outputs summary and redacted stats_overview.json.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))


def _fake_returns_and_meta(n_bars=60):
    np.random.seed(88)
    n_assets = 4
    idx = pd.date_range("2026-01-01", periods=n_bars, freq="1h")
    cols = ["BTC_spot", "ETH_spot"] + [f"pair_{i}" for i in range(n_assets)]
    data = np.random.randn(n_bars, len(cols)).astype(float) * 0.01
    returns_df = pd.DataFrame(data, index=idx, columns=cols)
    meta_df = pd.DataFrame(
        [{"asset_id": c, "label": c, "asset_type": "dex", "chain_id": "1", "pair_address": c} for c in cols]
    )
    return returns_df, meta_df


def _run_report(out_dir: Path, rw_enabled: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "csv").mkdir(exist_ok=True)
    (out_dir / "manifests").mkdir(exist_ok=True)
    (out_dir / "health").mkdir(exist_ok=True)
    argv = [
        "research_report_v2",
        "--freq",
        "1h",
        "--signals",
        "clean_momentum,value_vs_beta",
        "--portfolio",
        "simple",
        "--out-dir",
        str(out_dir),
        "--db",
        ":memory:",
        "--reality-check",
        "--execution-evidence",
        "--rc-n-sim",
        "25",
        "--rc-seed",
        "42",
        "--top-k",
        "2",
        "--bottom-k",
        "2",
    ]
    env = {"CRYPTO_ANALYZER_ENABLE_ROMANOWOLF": "1" if rw_enabled else "0"}
    with patch.dict(os.environ, env, clear=False):
        with (
            patch("crypto_analyzer.research_universe.get_research_assets", return_value=_fake_returns_and_meta()),
            patch("cli.research_report_v2.get_research_assets", return_value=_fake_returns_and_meta()),
            patch("cli.research_report_v2.get_factor_returns", return_value=None),
            patch("cli.research_report_v2.record_experiment_run"),
        ):
            sys.argv = argv
            from cli import research_report_v2

            research_report_v2.main()


def _redact_paths(obj, path_pattern: re.Pattern):
    if isinstance(obj, dict):
        return {k: _redact_paths(v, path_pattern) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_paths(x, path_pattern) for x in obj]
    if isinstance(obj, str) and path_pattern.search(obj):
        return "<path redacted>"
    return obj


def main():
    tmp = tempfile.mkdtemp(prefix="golden_stats_")
    base = Path(tmp)
    path_pattern = re.compile(r"[A-Za-z]:[/\\]|/home/|/tmp/|[/\\][\w.-]+[/\\]")
    results = {"rw_off": {}, "rw_on": {}, "stats_overview": None, "checks": []}

    try:
        # RW disabled
        out_off = base / "rw_off"
        _run_report(out_off, rw_enabled=False)
        rc_off = list((out_off / "csv").glob("reality_check_summary_*.json"))
        if rc_off:
            s_off = json.loads(rc_off[0].read_text(encoding="utf-8"))
            rw_adj_off = s_off.get("rw_adjusted_p_values")
            results["rw_off"]["rw_present"] = "rw_adjusted_p_values" in s_off
            results["rw_off"]["rw_empty_or_absent"] = rw_adj_off is None or (
                isinstance(rw_adj_off, dict) and len(rw_adj_off) == 0
            )
        else:
            results["rw_off"]["no_rc_file"] = True

        # RW enabled
        out_on = base / "rw_on"
        _run_report(out_on, rw_enabled=True)
        rc_on = list((out_on / "csv").glob("reality_check_summary_*.json"))
        if rc_on:
            s_on = json.loads(rc_on[0].read_text(encoding="utf-8"))
            rw_adj_on = s_on.get("rw_adjusted_p_values")
            results["rw_on"]["rw_present"] = "rw_adjusted_p_values" in s_on
            results["rw_on"]["rw_non_empty"] = isinstance(rw_adj_on, dict) and len(rw_adj_on) > 0
        else:
            results["rw_on"]["no_rc_file"] = True

        # Spot-check stats_overview (use rw_on run)
        so_path = out_on / "stats_overview.json"
        if so_path.exists():
            stats = json.loads(so_path.read_text(encoding="utf-8"))
            results["stats_overview"] = stats
            # Inequalities
            tot = stats.get("n_trials_eff_inputs_total")
            used = stats.get("n_trials_eff_inputs_used")
            if tot is not None and used is not None:
                results["checks"].append(f"n_trials_eff: {tot} >= {used} >= 1 -> {tot >= used >= 1}")
            total_splits = stats.get("pbo_cscv_total_splits")
            splits_used = stats.get("pbo_cscv_splits_used")
            if total_splits is not None and splits_used is not None:
                results["checks"].append(
                    f"pbo_cscv splits: {total_splits} >= {splits_used} -> {total_splits >= splits_used}"
                )
            else:
                results["checks"].append("pbo_cscv splits: (absent when CSCV skipped, e.g. T < S*4)")
            if stats.get("hac_skipped_reason"):
                t_null = stats.get("t_hac_mean_return") is None
                p_null = stats.get("p_hac_mean_return") is None
                results["checks"].append(f"HAC skipped: t/p null -> {t_null and p_null}")
            else:
                results["checks"].append("HAC ran: t/p present or N/A")
            results["checks"].append(f"rw_enabled in stats_overview: {stats.get('rw_enabled')}")
            # Break diagnostics: when n sufficient, file written and non-empty
            bd_written = stats.get("break_diagnostics_written")
            results["checks"].append(f"break_diagnostics_written: {bd_written}")
            if bd_written:
                bd_path = out_on / "break_diagnostics.json"
                assert bd_path.exists(), "break_diagnostics.json should exist when break_diagnostics_written is True"
                bd = json.loads(bd_path.read_text(encoding="utf-8"))
                assert bd.get("series"), "break_diagnostics.json should have non-empty series"
                results["checks"].append("break_diagnostics.json: exists and non-empty series")

        # Print summary
        print("=== Golden run summary ===\n")
        print("RW disabled:", results["rw_off"])
        print("RW enabled:", results["rw_on"])
        print("\nSpot-checks:", results["checks"])
        print("\n--- stats_overview.json (paths redacted) ---")
        if results["stats_overview"]:
            redacted = _redact_paths(results["stats_overview"], path_pattern)
            print(json.dumps(redacted, indent=2, sort_keys=True))
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
