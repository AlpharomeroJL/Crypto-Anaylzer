"""Regression: promotion evidence paths when artifacts live under reports/csv (reportv2 layout)."""

from __future__ import annotations

import json
from pathlib import Path

from crypto_analyzer.promotion.evidence_resolver import resolve_evidence
from crypto_analyzer.promotion.execution_evidence import ExecutionEvidence
from crypto_analyzer.validation_bundle import ValidationBundle


def _bundle_dict() -> dict:
    b = ValidationBundle(
        run_id="r1",
        dataset_id="d1",
        signal_name="sig",
        freq="1h",
        horizons=[1],
        ic_summary_by_horizon={1: {"mean_ic": 0.05, "t_stat": 3.0, "n_obs": 100}},
        ic_decay_table=[],
        meta={},
    )
    return b.to_dict()


def test_resolve_evidence_repo_relative_paths_with_bundle_parent_base(tmp_path, monkeypatch):
    """
    Same layout as golden run: stored paths are repo-root-relative (reports/csv/...),
    but evaluate passes evidence_base_path = parent(bundle) = reports/csv.
    Previously execution_evidence_path was joined as reports/csv/reports/csv/... and failed to load.
    """
    monkeypatch.chdir(tmp_path)
    csv_dir = tmp_path / "reports" / "csv"
    csv_dir.mkdir(parents=True)
    bundle_path = csv_dir / "validation_bundle_sig_r1.json"
    bundle_path.write_text(json.dumps(_bundle_dict(), sort_keys=True), encoding="utf-8")
    exec_path = csv_dir / "execution_evidence_sig_r1.json"
    exec_path.write_text(
        json.dumps(
            {
                "capacity_curve_path": "csv/capacity_sig_r1.csv",
                "cost_config": {
                    "fee_bps": 30,
                    "slippage_bps": 10,
                    "spread_vol_scale": 0.0,
                    "use_participation_impact": True,
                    "impact_bps_per_participation": 5.0,
                    "max_participation_pct": 10.0,
                },
                "max_participation_rate": 10.0,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    cap_path = csv_dir / "capacity_sig_r1.csv"
    cap_path.write_text("participation_pct,net_return\n0.0,0.0\n", encoding="utf-8")

    evidence = {
        "bundle_path": "reports/csv/validation_bundle_sig_r1.json",
        "execution_evidence_path": "reports/csv/execution_evidence_sig_r1.json",
    }
    base = Path(evidence["bundle_path"]).parent
    bundle, _reg, _rc, execution_evidence = resolve_evidence(
        evidence,
        base,
        evidence["bundle_path"],
    )
    assert bundle is not None
    assert bundle.signal_name == "sig"
    assert execution_evidence is not None
    assert execution_evidence.max_participation_rate == 10.0


def test_resolve_evidence_basename_only_next_to_bundle(tmp_path, monkeypatch):
    """When create stores only filenames and base is their directory (reports/csv)."""
    monkeypatch.chdir(tmp_path)
    csv_dir = tmp_path / "reports" / "csv"
    csv_dir.mkdir(parents=True)
    bundle_path = csv_dir / "vb.json"
    bundle_path.write_text(json.dumps(_bundle_dict(), sort_keys=True), encoding="utf-8")

    evidence = {"bundle_path": "vb.json"}
    base = Path("reports/csv")
    bundle, _, _, _ = resolve_evidence(evidence, base, "vb.json")
    assert bundle is not None


def test_execution_evidence_validate_capacity_reportv2_relative_to_out_dir(tmp_path):
    """capacity_curve_path is relative to report out_dir (reports/), base from CLI is reports/csv."""
    csv_dir = tmp_path / "reports" / "csv"
    csv_dir.mkdir(parents=True)
    cap_file = csv_dir / "capacity_curve_sig_r1.csv"
    cap_file.write_text("participation_pct,net_return\n0.0,0.0\n", encoding="utf-8")
    ev = ExecutionEvidence(
        max_participation_rate=10.0,
        capacity_curve_path="csv/capacity_curve_sig_r1.csv",
        cost_config={
            "fee_bps": 30,
            "slippage_bps": 10,
            "spread_vol_scale": 0.0,
            "use_participation_impact": True,
            "impact_bps_per_participation": 5.0,
            "max_participation_pct": 10.0,
        },
    )
    base = tmp_path / "reports" / "csv"
    assert ev.validate_required(base_path=base) == []
