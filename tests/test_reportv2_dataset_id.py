"""Tests that reportv2 experiment recording includes dataset_id."""
import sqlite3
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.experiments import record_experiment_run, load_experiments
from crypto_analyzer.dataset import get_dataset_id


def test_experiment_row_includes_dataset_id(tmp_path):
    """When dataset_id is provided, it should appear in the experiment row."""
    db = str(tmp_path / "experiments.db")
    row = {
        "run_id": "test_run_001",
        "ts_utc": "2026-01-01T00:00:00+00:00",
        "git_commit": "abc123",
        "spec_version": "5.0",
        "out_dir": "reports",
        "notes": "",
        "data_start": "2026-01-01",
        "data_end": "2026-01-02",
        "config_hash": "deadbeef",
        "env_fingerprint": "{}",
        "hypothesis": "",
        "tags_json": [],
        "dataset_id": "abcdef1234567890",
        "params_json": {"freq": "1h"},
    }
    record_experiment_run(db, row, metrics_dict={"sharpe": 1.5})
    df = load_experiments(db)
    assert not df.empty
    assert df.iloc[0]["dataset_id"] == "abcdef1234567890"


def test_explicit_dataset_id_overrides_computed(tmp_path):
    """Explicit --dataset-id should take precedence over computed."""
    db = str(tmp_path / "experiments.db")
    explicit_id = "explicit_override"
    row = {
        "run_id": "test_run_002",
        "ts_utc": "2026-01-01T00:00:00+00:00",
        "dataset_id": explicit_id,
    }
    record_experiment_run(db, row)
    df = load_experiments(db)
    assert df.iloc[0]["dataset_id"] == explicit_id


def test_computed_dataset_id_is_stable(tmp_path):
    """get_dataset_id should return consistent results."""
    db = str(tmp_path / "data.sqlite")
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE sol_monitor_snapshots (ts_utc TEXT)")
        conn.execute("INSERT INTO sol_monitor_snapshots VALUES ('2026-01-01')")
        conn.commit()
    id1 = get_dataset_id(db)
    id2 = get_dataset_id(db)
    assert id1 == id2
    assert len(id1) == 16
