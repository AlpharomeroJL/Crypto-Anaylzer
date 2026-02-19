"""
Tests for the SQLite experiment registry (crypto_analyzer.experiments).
Uses a temp file for isolation.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.experiments import (
    ensure_experiment_tables,
    load_distinct_metric_names,
    load_experiment_metrics,
    load_experiments,
    load_metric_history,
    record_experiment_run,
)


@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "test_experiments.db")


class TestEnsureTables:
    def test_creates_tables(self, tmp_db):
        with sqlite3.connect(tmp_db) as conn:
            ensure_experiment_tables(conn)
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "experiments" in tables
        assert "experiment_metrics" in tables
        assert "experiment_artifacts" in tables

    def test_idempotent(self, tmp_db):
        with sqlite3.connect(tmp_db) as conn:
            ensure_experiment_tables(conn)
            ensure_experiment_tables(conn)


class TestRecordAndLoad:
    def test_record_and_load_experiment(self, tmp_db):
        row = {
            "run_id": "abc123",
            "ts_utc": "2025-01-15T12:00:00+00:00",
            "git_commit": "deadbeef",
            "spec_version": "5.0",
            "out_dir": "reports",
            "notes": "test run",
            "data_start": "2024-12-01",
            "data_end": "2025-01-15",
            "config_hash": "cfghash",
            "env_fingerprint": "py3.10",
        }
        metrics = {"sharpe": 1.23, "max_drawdown": 0.05, "mean_ic": 0.04}
        artifacts = [
            {"artifact_path": "reports/report.md", "sha256": "aaa"},
            {"artifact_path": "reports/health.json", "sha256": "bbb"},
        ]

        run_id = record_experiment_run(tmp_db, row, metrics, artifacts)
        assert run_id == "abc123"

        df = load_experiments(tmp_db, limit=10)
        assert len(df) == 1
        assert df.iloc[0]["run_id"] == "abc123"
        assert df.iloc[0]["git_commit"] == "deadbeef"
        assert df.iloc[0]["spec_version"] == "5.0"

    def test_load_experiment_metrics(self, tmp_db):
        row = {"run_id": "run1", "ts_utc": "2025-01-01T00:00:00+00:00"}
        metrics = {"sharpe": 2.0, "turnover": 0.15}
        record_experiment_run(tmp_db, row, metrics)

        mdf = load_experiment_metrics(tmp_db, "run1")
        assert len(mdf) == 2
        assert set(mdf["metric_name"].tolist()) == {"sharpe", "turnover"}
        sharpe_val = mdf[mdf["metric_name"] == "sharpe"]["metric_value"].iloc[0]
        assert abs(sharpe_val - 2.0) < 1e-6

    def test_upsert_overwrites(self, tmp_db):
        row = {"run_id": "dup1", "ts_utc": "2025-02-01T00:00:00+00:00", "notes": "first"}
        record_experiment_run(tmp_db, row, {"sharpe": 1.0})

        row2 = {"run_id": "dup1", "ts_utc": "2025-02-01T00:00:00+00:00", "notes": "updated"}
        record_experiment_run(tmp_db, row2, {"sharpe": 2.0})

        df = load_experiments(tmp_db)
        assert len(df) == 1
        assert df.iloc[0]["notes"] == "updated"

        mdf = load_experiment_metrics(tmp_db, "dup1")
        assert len(mdf) == 1
        assert abs(mdf.iloc[0]["metric_value"] - 2.0) < 1e-6

    def test_load_metric_history(self, tmp_db):
        for i in range(5):
            row = {"run_id": f"run_{i}", "ts_utc": f"2025-01-0{i + 1}T00:00:00+00:00"}
            record_experiment_run(tmp_db, row, {"sharpe": float(i)})

        hist = load_metric_history(tmp_db, "sharpe", limit=100)
        assert len(hist) == 5
        assert "ts_utc" in hist.columns
        assert "metric_value" in hist.columns

    def test_distinct_metric_names(self, tmp_db):
        row = {"run_id": "r1", "ts_utc": "2025-01-01T00:00:00+00:00"}
        record_experiment_run(tmp_db, row, {"alpha": 0.1, "beta": 0.2, "gamma": 0.3})
        names = load_distinct_metric_names(tmp_db)
        assert names == ["alpha", "beta", "gamma"]

    def test_no_db_returns_empty(self):
        df = load_experiments("/nonexistent/path/db.sqlite")
        assert df.empty

    def test_artifacts_stored(self, tmp_db):
        row = {"run_id": "art1", "ts_utc": "2025-03-01T00:00:00+00:00"}
        arts = [{"artifact_path": "a.md", "sha256": "hash1"}]
        record_experiment_run(tmp_db, row, {}, arts)

        with sqlite3.connect(tmp_db) as conn:
            rows = conn.execute("SELECT * FROM experiment_artifacts WHERE run_id='art1'").fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "a.md"
        assert rows[0][2] == "hash1"
