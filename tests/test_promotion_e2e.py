"""E2E: create candidate from bundle path, evaluate with RC/regime/execution evidence, assert stored decision."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.db.migrations_phase3 import run_migrations_phase3
from crypto_analyzer.promotion.gating import ThresholdConfig
from crypto_analyzer.promotion.service import evaluate_and_record
from crypto_analyzer.promotion.store_sqlite import create_candidate, get_candidate, get_events
from crypto_analyzer.validation_bundle import ValidationBundle


def _write_bundle(path: Path, mean_ic: float = 0.03, t_stat: float = 3.0) -> None:
    bundle = ValidationBundle(
        run_id="run_e2e",
        dataset_id="ds_e2e",
        signal_name="momentum_24h",
        freq="1h",
        horizons=[1],
        ic_summary_by_horizon={1: {"mean_ic": mean_ic, "t_stat": t_stat, "n_obs": 300}},
        ic_decay_table=[],
        meta={"config_hash": "xyz", "git_commit": "abc"},
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bundle.to_dict(), f, sort_keys=True)


def test_e2e_create_evaluate_with_rc_summary():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "prom.sqlite"
        bundle_path = Path(tmp) / "reports" / "bundle.json"
        _write_bundle(bundle_path)
        conn = sqlite3.connect(db_path)
        run_migrations(conn, db_path)
        run_migrations_phase3(conn, db_path)
        evidence = {"bundle_path": str(bundle_path), "validation_bundle_path": str(bundle_path)}
        cid = create_candidate(
            conn,
            dataset_id="ds_e2e",
            run_id="run_e2e",
            signal_name="momentum_24h",
            horizon=1,
            config_hash="xyz",
            git_commit="abc",
            evidence=evidence,
        )
        conn.close()

        thresholds = ThresholdConfig(require_reality_check=True, max_rc_p_value=0.05)
        rc_summary = {"rc_p_value": 0.02}
        conn2 = sqlite3.connect(db_path)
        decision = evaluate_and_record(
            conn2,
            cid,
            thresholds,
            str(bundle_path),
            rc_summary=rc_summary,
            evidence_base_path=bundle_path.parent,
        )
        conn2.close()
        assert decision.status == "accepted"
        conn3 = sqlite3.connect(db_path)
        row = get_candidate(conn3, cid)
        events = get_events(conn3, cid)
        conn3.close()
        assert row["status"] == "accepted"
        eval_ev = [e for e in events if e["event_type"] == "evaluated"]
        assert len(eval_ev) == 1


def test_e2e_execution_evidence_required_accept_when_present():
    """Create candidate with execution_evidence_path and real capacity_curve.csv => accept when require-exec."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        db_path = tmp / "prom.sqlite"
        bundle_path = tmp / "reports" / "bundle.json"
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        _write_bundle(bundle_path)
        # Write capacity curve CSV and execution_evidence.json
        csv_dir = tmp / "reports" / "csv"
        csv_dir.mkdir(parents=True, exist_ok=True)
        (csv_dir / "capacity_curve_sig_run1.csv").write_text(
            "notional_multiplier,sharpe_annual\n1.0,0.5\n2.0,0.4\n5.0,0.3\n"
        )
        # Path relative to tmp so base_path / path resolves to the file
        cap_rel = str((csv_dir / "capacity_curve_sig_run1.csv").relative_to(tmp))
        exec_ev = {
            "capacity_curve_path": cap_rel.replace("\\", "/"),
            "max_participation_rate": 10.0,
            "cost_config": {"fee_bps": 30, "slippage_bps": 10},
        }
        exec_ev_path = csv_dir / "execution_evidence_sig_run1.json"
        with open(exec_ev_path, "w", encoding="utf-8") as f:
            json.dump(exec_ev, f, sort_keys=True)
        exec_ev_path_rel = str(exec_ev_path.relative_to(tmp)).replace("\\", "/")
        evidence = {
            "bundle_path": str(bundle_path),
            "validation_bundle_path": str(bundle_path),
            "execution_evidence_path": exec_ev_path_rel,
        }
        conn = sqlite3.connect(db_path)
        run_migrations(conn, db_path)
        run_migrations_phase3(conn, db_path)
        cid = create_candidate(
            conn,
            dataset_id="ds_e2e",
            run_id="run_e2e",
            signal_name="sig",
            horizon=1,
            config_hash="xyz",
            git_commit="abc",
            evidence=evidence,
            evidence_base_path=tmp,
        )
        conn.close()
        thresholds = ThresholdConfig(
            ic_mean_min=0.02,
            tstat_min=2.0,
            require_execution_evidence=True,
        )
        conn2 = sqlite3.connect(db_path)
        decision = evaluate_and_record(
            conn2,
            cid,
            thresholds,
            str(bundle_path),
            evidence_base_path=tmp,
            target_status="accepted",
        )
        conn2.close()
        assert decision.status == "accepted", decision.reasons


def test_e2e_execution_evidence_required_reject_when_missing():
    """Candidate without execution_evidence_path => reject when require-exec."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        db_path = tmp / "prom.sqlite"
        bundle_path = tmp / "reports" / "bundle.json"
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        _write_bundle(bundle_path)
        evidence = {"bundle_path": str(bundle_path), "validation_bundle_path": str(bundle_path)}
        conn = sqlite3.connect(db_path)
        run_migrations(conn, db_path)
        run_migrations_phase3(conn, db_path)
        cid = create_candidate(
            conn,
            dataset_id="ds_e2e",
            run_id="run_e2e",
            signal_name="sig",
            horizon=1,
            config_hash="xyz",
            git_commit="abc",
            evidence=evidence,
        )
        conn.execute("UPDATE promotion_candidates SET status = ? WHERE candidate_id = ?", ("candidate", cid))
        conn.commit()
        conn.close()
        thresholds = ThresholdConfig(
            ic_mean_min=0.02,
            tstat_min=2.0,
            require_execution_evidence=True,
        )
        conn2 = sqlite3.connect(db_path)
        decision = evaluate_and_record(
            conn2,
            cid,
            thresholds,
            str(bundle_path),
            evidence_base_path=bundle_path.parent,
            target_status="accepted",
        )
        conn2.close()
        assert decision.status == "rejected"
        assert any("execution evidence" in r.lower() for r in decision.reasons)
