"""Tests for the pluggable ExperimentStore abstraction (SQLite + factory)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crypto_analyzer.experiment_store import (
    PostgresExperimentStore,
    SQLiteExperimentStore,
    get_experiment_store,
)


@pytest.fixture
def store(tmp_path) -> SQLiteExperimentStore:
    return SQLiteExperimentStore(db_path=str(tmp_path / "store.db"))


class TestSQLiteStoreBasic:
    def test_sqlite_store_record_and_load(self, store):
        row = {
            "run_id": "s1",
            "ts_utc": "2025-08-01T00:00:00+00:00",
            "hypothesis": "test hypothesis",
            "tags_json": ["fast", "slow"],
        }
        rid = store.record_run(row, metrics_dict={"sharpe": 1.5})
        assert rid == "s1"

        df = store.load_runs(limit=10)
        assert len(df) == 1
        assert df.iloc[0]["run_id"] == "s1"

    def test_sqlite_store_metrics(self, store):
        row = {"run_id": "m1", "ts_utc": "2025-08-02T00:00:00+00:00"}
        store.record_run(row, metrics_dict={"sharpe": 2.0, "max_dd": 0.1})

        mdf = store.load_metrics("m1")
        assert len(mdf) == 2
        assert set(mdf["metric_name"].tolist()) == {"sharpe", "max_dd"}

    def test_sqlite_store_metric_history(self, store):
        for i in range(3):
            row = {"run_id": f"h{i}", "ts_utc": f"2025-09-0{i + 1}T00:00:00+00:00"}
            store.record_run(row, metrics_dict={"alpha": float(i)})

        hist = store.load_metric_history("alpha", limit=100)
        assert len(hist) == 3

    def test_sqlite_store_distinct_metric_names(self, store):
        row = {"run_id": "d1", "ts_utc": "2025-10-01T00:00:00+00:00"}
        store.record_run(row, metrics_dict={"x": 1.0, "y": 2.0, "z": 3.0})
        assert store.load_distinct_metric_names() == ["x", "y", "z"]


class TestPostgresGracefulFailure:
    def test_postgres_store_graceful_failure(self):
        with pytest.raises(Exception):
            PostgresExperimentStore(dsn="postgresql://bad:bad@localhost:1/nope")


class TestFactory:
    def test_get_experiment_store_default_sqlite(self, monkeypatch, tmp_path):
        monkeypatch.delenv("EXPERIMENT_DB_DSN", raising=False)
        monkeypatch.setenv("EXPERIMENT_DB_PATH", str(tmp_path / "factory.db"))

        store = get_experiment_store()
        assert isinstance(store, SQLiteExperimentStore)
