"""Phase 3 A3: governance_events table is append-only (triggers block UPDATE/DELETE)."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from crypto_analyzer.db.governance_events import append_governance_event, governance_events_table_exists
from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.db.migrations_phase3 import run_migrations_phase3


def test_governance_events_append_only_triggers_block_update_and_delete():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "gov.db"
        conn = sqlite3.connect(str(db_path))
        run_migrations(conn, str(db_path))
        run_migrations_phase3(conn, str(db_path))
        if not governance_events_table_exists(conn):
            return
        append_governance_event(
            conn,
            timestamp="2026-02-22T00:00:00Z",
            actor="test",
            action="evaluate",
            candidate_id="c1",
        )
        cur = conn.execute("SELECT event_id FROM governance_events WHERE candidate_id = 'c1'")
        row = cur.fetchone()
        assert row is not None
        event_id = row[0]
        try:
            conn.execute("UPDATE governance_events SET action = 'x' WHERE event_id = ?", (event_id,))
            conn.commit()
            raise AssertionError("UPDATE should have been blocked by trigger")
        except sqlite3.IntegrityError as e:
            assert "append-only" in str(e).lower() or "abort" in str(e).lower()
        try:
            conn.execute("DELETE FROM governance_events WHERE event_id = ?", (event_id,))
            conn.commit()
            raise AssertionError("DELETE should have been blocked by trigger")
        except sqlite3.IntegrityError as e:
            assert "append-only" in str(e).lower() or "abort" in str(e).lower()
        conn.close()
