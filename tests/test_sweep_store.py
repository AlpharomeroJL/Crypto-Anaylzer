"""Sweep registry store: persist_sweep_family only when Phase 3 tables exist."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.db.migrations_phase3 import run_migrations_phase3
from crypto_analyzer.sweeps.hypothesis_id import compute_hypothesis_id
from crypto_analyzer.sweeps.store_sqlite import persist_sweep_family, sweep_registry_tables_exist


def test_sweep_registry_tables_exist_false_without_phase3():
    """Without Phase 3 migrations, sweep_registry_tables_exist is False."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        assert sweep_registry_tables_exist(conn) is False
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)


def test_sweep_registry_tables_exist_true_after_phase3():
    """After run_migrations_phase3, sweep_registry_tables_exist is True."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        run_migrations_phase3(conn, path)
        assert sweep_registry_tables_exist(conn) is True
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)


def test_persist_sweep_family_returns_false_without_phase3():
    """persist_sweep_family returns False when sweep tables do not exist."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        ok = persist_sweep_family(
            conn,
            family_id="rcfam_abc",
            dataset_id="ds1",
            sweep_payload_json="{}",
            hypotheses=[{"hypothesis_id": "hyp_1", "signal_name": "s", "horizon": 1}],
        )
        assert ok is False
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)


def test_persist_sweep_family_inserts_when_phase3():
    """persist_sweep_family inserts sweep_families and sweep_hypotheses when tables exist."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        run_migrations_phase3(conn, path)
        hid = compute_hypothesis_id({"signal_name": "mom", "horizon": 1, "regime_run_id": ""})
        hypotheses = [
            {
                "hypothesis_id": hid,
                "signal_name": "mom",
                "horizon": 1,
                "estimator": None,
                "params_json": None,
                "regime_run_id": None,
            },
        ]
        ok = persist_sweep_family(
            conn,
            family_id="rcfam_xyz",
            dataset_id="ds1",
            sweep_payload_json='{"signals":["mom"],"horizons":[1]}',
            run_id="run1",
            git_commit="abc",
            config_hash="h16",
            hypotheses=hypotheses,
        )
        assert ok is True
        cur = conn.execute(
            "SELECT family_id, dataset_id, run_id FROM sweep_families WHERE family_id = ?", ("rcfam_xyz",)
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "rcfam_xyz"
        assert row[1] == "ds1"
        assert row[2] == "run1"
        cur = conn.execute(
            "SELECT family_id, hypothesis_id, signal_name, horizon FROM sweep_hypotheses WHERE family_id = ?",
            ("rcfam_xyz",),
        )
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0][2] == "mom" and rows[0][3] == 1
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)
