"""Phase 3 migrations: not applied by default; apply only via run_migrations_phase3 when regimes enabled."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.db.migrations_phase3 import (
    MIGRATIONS_PHASE3,
    _max_applied_version_phase3,
    _schema_migrations_phase3_exists,
    run_migrations_phase3,
)
from crypto_analyzer.promotion.store_sqlite import (
    create_candidate,
    insert_eligibility_report,
    promote_to_accepted,
)


def test_default_run_migrations_does_not_create_phase3_tables():
    """run_migrations() must NOT create regime_runs, regime_states, or schema_migrations_phase3."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('regime_runs','regime_states','schema_migrations_phase3')"
        )
        phase3_tables = [r[0] for r in cur.fetchall()]
        assert "regime_runs" not in phase3_tables
        assert "regime_states" not in phase3_tables
        assert "schema_migrations_phase3" not in phase3_tables
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)


def test_run_migrations_phase3_creates_tables_and_records():
    """Explicit run_migrations_phase3(): regime_runs, regime_states, schema_migrations_phase3 exist."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        run_migrations_phase3(conn, path)
        assert _schema_migrations_phase3_exists(conn)
        assert _max_applied_version_phase3(conn) == len(MIGRATIONS_PHASE3)
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('regime_runs','regime_states','promotion_candidates','promotion_events','sweep_families','sweep_hypotheses')"
        )
        tables = [r[0] for r in cur.fetchall()]
        assert "regime_runs" in tables
        assert "regime_states" in tables
        assert "promotion_candidates" in tables
        assert "promotion_events" in tables
        assert "sweep_families" in tables
        assert "sweep_hypotheses" in tables
        cur = conn.execute("PRAGMA table_info(promotion_candidates)")
        cols = [r[1] for r in cur.fetchall()]
        for c in (
            "candidate_id",
            "created_at_utc",
            "status",
            "dataset_id",
            "run_id",
            "signal_name",
            "horizon",
            "config_hash",
            "git_commit",
            "evidence_json",
        ):
            assert c in cols
        cur = conn.execute("PRAGMA table_info(promotion_events)")
        cols_ev = [r[1] for r in cur.fetchall()]
        for c in ("event_id", "candidate_id", "ts_utc", "event_type", "payload_json"):
            assert c in cols_ev
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)


def test_run_migrations_phase3_rerun_idempotent():
    """Rerun run_migrations_phase3 -> same version count, no duplicate migration rows."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        run_migrations_phase3(conn, path)
        max_before = _max_applied_version_phase3(conn)
        cur = conn.execute("SELECT COUNT(*) FROM schema_migrations_phase3")
        count_before = cur.fetchone()[0]
        conn.close()

        conn2 = sqlite3.connect(path)
        run_migrations_phase3(conn2, path)
        max_after = _max_applied_version_phase3(conn2)
        cur = conn2.execute("SELECT COUNT(*) FROM schema_migrations_phase3")
        count_after = cur.fetchone()[0]
        conn2.close()

        assert max_after == max_before
        assert count_after == count_before
    finally:
        Path(path).unlink(missing_ok=True)


def test_trigger_blocks_direct_update_to_candidate_without_eligibility_report():
    """Phase 1: direct UPDATE promotion_candidates SET status='candidate' without eligibility_report_id is blocked by trigger."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        run_migrations_phase3(conn, path)
        cid = create_candidate(
            conn,
            dataset_id="ds1",
            run_id="run1",
            signal_name="sig",
            horizon=1,
            config_hash="x",
            git_commit="y",
        )
        conn.commit()
        # Trigger: UPDATE status to candidate without eligibility_report_id must raise (IntegrityError for RAISE(ABORT))
        try:
            conn.execute(
                "UPDATE promotion_candidates SET status = ? WHERE candidate_id = ?",
                ("candidate", cid),
            )
            conn.commit()
        except (sqlite3.IntegrityError, sqlite3.OperationalError) as e:
            assert "eligibility" in str(e).lower() or "abort" in str(e).lower()
            return
        assert False, (
            "Expected IntegrityError/OperationalError from trigger when setting status=candidate without eligibility_report_id"
        )
    finally:
        conn.close()
        Path(path).unlink(missing_ok=True)


def test_trigger_blocks_delete_eligibility_report_when_referenced():
    """Phase 1: DELETE from eligibility_reports referenced by candidate/accepted is blocked (evidence immutability)."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        run_migrations_phase3(conn, path)
        cid = create_candidate(
            conn,
            dataset_id="ds1",
            run_id="run1",
            signal_name="sig",
            horizon=1,
            config_hash="x",
            git_commit="y",
        )
        conn.commit()
        report_id = "elig_immutable_test_001"
        insert_eligibility_report(
            conn,
            report_id,
            cid,
            "accepted",
            True,
            "[]",
            "[]",
            "2026-02-01T12:00:00Z",
            run_key="rk1",
            run_instance_id="run1",
            dataset_id_v2="d2",
            engine_version="v1",
            config_version="c1",
        )
        promote_to_accepted(conn, cid, report_id, reason="test")
        conn.commit()
        try:
            conn.execute("DELETE FROM eligibility_reports WHERE eligibility_report_id = ?", (report_id,))
            conn.commit()
        except (sqlite3.IntegrityError, sqlite3.OperationalError) as e:
            assert "immutable" in str(e).lower() or "delete" in str(e).lower() or "abort" in str(e).lower()
            return
        assert False, "Expected trigger to block DELETE of referenced eligibility report"
    finally:
        conn.close()
        Path(path).unlink(missing_ok=True)
