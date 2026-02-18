"""Tests for new experiment metadata columns: hypothesis, tags, dataset_id, params."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crypto_analyzer.experiments import (
    ensure_experiment_tables,
    load_experiments_filtered,
    parse_tags,
    record_experiment_run,
)


_OLD_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experiments (
    run_id          TEXT PRIMARY KEY,
    ts_utc          TEXT NOT NULL,
    git_commit      TEXT,
    spec_version    TEXT,
    out_dir         TEXT,
    notes           TEXT,
    data_start      TEXT,
    data_end        TEXT,
    config_hash     TEXT,
    env_fingerprint TEXT
);
CREATE TABLE IF NOT EXISTS experiment_metrics (
    run_id       TEXT NOT NULL,
    metric_name  TEXT NOT NULL,
    metric_value REAL,
    PRIMARY KEY (run_id, metric_name)
);
CREATE TABLE IF NOT EXISTS experiment_artifacts (
    run_id        TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    sha256        TEXT,
    PRIMARY KEY (run_id, artifact_path)
);
"""


@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "test_meta.db")


class TestMigration:
    def test_migration_adds_columns(self, tmp_path):
        db = str(tmp_path / "old.db")
        with sqlite3.connect(db) as conn:
            conn.executescript(_OLD_SCHEMA_SQL)

        with sqlite3.connect(db) as conn:
            ensure_experiment_tables(conn)

        with sqlite3.connect(db) as conn:
            info = conn.execute("PRAGMA table_info(experiments)").fetchall()
            col_names = {row[1] for row in info}

        for col in ("hypothesis", "tags_json", "dataset_id", "params_json"):
            assert col in col_names, f"Missing column after migration: {col}"


class TestTagsAndHypothesis:
    def test_tags_stored_and_loaded(self, tmp_db):
        row = {
            "run_id": "tag1",
            "ts_utc": "2025-06-01T00:00:00+00:00",
            "tags_json": ["alpha", "momentum"],
        }
        record_experiment_run(tmp_db, row)

        df = load_experiments_filtered(tmp_db)
        stored = df.loc[df["run_id"] == "tag1", "tags_json"].iloc[0]
        parsed = json.loads(stored)
        assert "alpha" in parsed
        assert "momentum" in parsed

    def test_hypothesis_stored(self, tmp_db):
        row = {
            "run_id": "hyp1",
            "ts_utc": "2025-06-02T00:00:00+00:00",
            "hypothesis": "test idea",
        }
        record_experiment_run(tmp_db, row)

        df = load_experiments_filtered(tmp_db)
        assert df.loc[df["run_id"] == "hyp1", "hypothesis"].iloc[0] == "test idea"


class TestParseTags:
    def test_parse_tags(self):
        assert parse_tags("a, b , c") == ["a", "b", "c"]

    def test_parse_tags_empty(self):
        assert parse_tags("") == []


class TestFiltering:
    @pytest.fixture(autouse=True)
    def _seed(self, tmp_db):
        self.db = tmp_db
        rows = [
            {"run_id": "r1", "ts_utc": "2025-07-01T00:00:00+00:00",
             "tags_json": ["alpha", "value"], "hypothesis": "momentum works"},
            {"run_id": "r2", "ts_utc": "2025-07-02T00:00:00+00:00",
             "tags_json": ["beta"], "hypothesis": "reversion idea"},
            {"run_id": "r3", "ts_utc": "2025-07-03T00:00:00+00:00",
             "tags_json": ["alpha", "quality"], "hypothesis": "quality factor"},
        ]
        for r in rows:
            record_experiment_run(self.db, r)

    def test_filter_by_tag(self):
        df = load_experiments_filtered(self.db, tag="alpha")
        assert set(df["run_id"].tolist()) == {"r1", "r3"}

    def test_filter_by_search(self):
        df = load_experiments_filtered(self.db, search="reversion")
        assert len(df) == 1
        assert df.iloc[0]["run_id"] == "r2"
