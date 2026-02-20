"""Promotion store_sqlite: create, list, get, update_status, record_event, get_events."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.db.migrations_phase3 import run_migrations_phase3
from crypto_analyzer.promotion.store_sqlite import (
    create_candidate,
    get_candidate,
    get_events,
    list_candidates,
    record_event,
    require_promotion_tables,
    update_status,
)


@pytest.fixture
def conn_with_promotion():
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        run_migrations_phase3(conn, path)
        yield conn
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)


def test_create_candidate_returns_id(conn_with_promotion):
    conn = conn_with_promotion
    cid = create_candidate(
        conn,
        dataset_id="ds1",
        run_id="run1",
        signal_name="sig_a",
        horizon=1,
        config_hash="abc",
        git_commit="def",
    )
    assert cid.startswith("prom_")
    assert len(cid) > 10


def test_require_promotion_tables_raises_when_missing():
    """Store fails fast with clear message when promotion tables do not exist."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        # Do not run run_migrations_phase3
        with pytest.raises(RuntimeError) as exc_info:
            require_promotion_tables(conn)
        assert "run_migrations_phase3" in str(exc_info.value)
        assert "promotion" in str(exc_info.value).lower()
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)


def test_get_candidate(conn_with_promotion):
    conn = conn_with_promotion
    cid = create_candidate(
        conn,
        dataset_id="ds1",
        run_id="run1",
        signal_name="sig_a",
        horizon=1,
        config_hash="abc",
        git_commit="def",
        evidence={"bundle_path": "/p/bundle.json"},
    )
    row = get_candidate(conn, cid)
    assert row is not None
    assert row["candidate_id"] == cid
    assert row["signal_name"] == "sig_a"
    assert row["status"] == "exploratory"
    assert "bundle_path" in (row.get("evidence_json") or "")


def test_evidence_paths_relativized_when_base_given(conn_with_promotion):
    """Paths in evidence are stored relative to evidence_base_path when provided."""
    conn = conn_with_promotion
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp).resolve()
        abs_bundle = base / "reports" / "bundle.json"
        abs_bundle.parent.mkdir(parents=True, exist_ok=True)
        abs_rc = base / "reports" / "rc.json"
        evidence = {"bundle_path": str(abs_bundle), "rc_summary_path": str(abs_rc)}
        cid = create_candidate(
            conn,
            dataset_id="ds1",
            run_id="run1",
            signal_name="s",
            horizon=1,
            config_hash="x",
            git_commit="y",
            evidence=evidence,
            evidence_base_path=base,
        )
    row = get_candidate(conn, cid)
    ev = json.loads(row["evidence_json"]) if row.get("evidence_json") else {}
    # When path is under base, stored relative (no leading slash / drive)
    assert ev.get("bundle_path") and not os.path.isabs(ev["bundle_path"])
    assert "bundle.json" in ev["bundle_path"]
    assert ev.get("rc_summary_path") and not os.path.isabs(ev["rc_summary_path"])


def test_list_candidates_filter(conn_with_promotion):
    conn = conn_with_promotion
    create_candidate(conn, dataset_id="ds1", run_id="r1", signal_name="s1", horizon=1, config_hash="x", git_commit="y")
    create_candidate(conn, dataset_id="ds1", run_id="r2", signal_name="s2", horizon=2, config_hash="x", git_commit="y")
    create_candidate(conn, dataset_id="ds2", run_id="r3", signal_name="s1", horizon=1, config_hash="x", git_commit="y")
    all_rows = list_candidates(conn, limit=10)
    assert len(all_rows) == 3
    by_status = list_candidates(conn, status="exploratory", limit=10)
    assert len(by_status) == 3
    by_signal = list_candidates(conn, signal_name="s1", limit=10)
    assert len(by_signal) == 2


def test_update_status_and_record_event(conn_with_promotion):
    conn = conn_with_promotion
    cid = create_candidate(
        conn,
        dataset_id="ds1",
        run_id="run1",
        signal_name="sig_a",
        horizon=1,
        config_hash="abc",
        git_commit="def",
    )
    events_before = get_events(conn, cid)
    assert len(events_before) >= 1  # created
    update_status(conn, cid, "accepted", reason="passed gates")
    row = get_candidate(conn, cid)
    assert row["status"] == "accepted"
    events_after = get_events(conn, cid)
    assert len(events_after) > len(events_before)
    event_types = [e["event_type"] for e in events_after]
    assert "status_change" in event_types


def test_events_append_only(conn_with_promotion):
    conn = conn_with_promotion
    cid = create_candidate(
        conn,
        dataset_id="ds1",
        run_id="run1",
        signal_name="sig_a",
        horizon=1,
        config_hash="abc",
        git_commit="def",
    )
    record_event(conn, cid, "custom", {"a": 1})
    record_event(conn, cid, "custom", {"b": 2})
    events = get_events(conn, cid)
    event_ids = [e["event_id"] for e in events]
    assert event_ids == sorted(event_ids)
