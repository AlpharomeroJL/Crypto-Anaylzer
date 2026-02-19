"""Smoke tests for the research API endpoints."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from starlette.testclient import TestClient  # noqa: E402

from crypto_analyzer.api import app  # noqa: E402


@pytest.fixture()
def _temp_dbs(tmp_path, monkeypatch):
    db_file = tmp_path / "test.sqlite"
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute("CREATE TABLE universe_allowlist (pair_address TEXT, base_symbol TEXT, quote_symbol TEXT)")
        conn.execute(
            "INSERT INTO universe_allowlist VALUES (?, ?, ?)",
            ("0xabc", "SOL", "USDC"),
        )

    exp_db = tmp_path / "experiments.db"
    with sqlite3.connect(str(exp_db)) as conn:
        from crypto_analyzer.experiments import ensure_experiment_tables

        ensure_experiment_tables(conn)

    monkeypatch.setattr("crypto_analyzer.api._db_path", lambda: str(db_file))
    monkeypatch.setenv("EXPERIMENT_DB_PATH", str(exp_db))
    monkeypatch.setattr("crypto_analyzer.api._experiment_db", lambda: str(exp_db))


@pytest.fixture()
def client(_temp_dbs):
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_allowlist(client):
    resp = client.get("/latest/allowlist")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) >= 1
    assert rows[0]["base_symbol"] == "SOL"


def test_experiments_recent(client):
    resp = client.get("/experiments/recent")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_experiment_not_found(client):
    resp = client.get("/experiments/nonexistent")
    assert resp.status_code == 404


def test_metric_history(client):
    resp = client.get("/metrics/sharpe/history")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
