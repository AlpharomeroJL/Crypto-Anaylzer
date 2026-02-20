"""
Tests for ingest PollContext lifecycle: close() idempotence, context manager, rollback on exception.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from crypto_analyzer.ingest import get_poll_context, run_one_cycle


def test_close_is_idempotent(tmp_path: Path) -> None:
    """Calling close() multiple times does not raise and leaves context closed."""
    db = str(tmp_path / "test.db")
    ctx = get_poll_context(db)
    assert not ctx._closed
    ctx.close()
    assert ctx._closed
    ctx.close()
    ctx.close()
    assert ctx._closed


def test_context_manager_closes_on_success(tmp_path: Path) -> None:
    """With block exits normally: connection is closed."""
    db = str(tmp_path / "test.db")
    with get_poll_context(db) as ctx:
        assert not ctx._closed
        assert ctx.conn.execute("SELECT 1").fetchone() == (1,)
    assert ctx._closed


def test_context_manager_rollback_and_close_on_exception(tmp_path: Path) -> None:
    """On exception, __exit__ rolls back and closes connection."""
    db = str(tmp_path / "test.db")
    with pytest.raises(ValueError, match="oops"):
        with get_poll_context(db) as ctx:
            raise ValueError("oops")
    assert ctx._closed


def test_run_one_cycle_rollback_on_exception(tmp_path: Path) -> None:
    """If run_one_cycle fails before commit (e.g. health upsert raises), conn is rolled back."""
    import logging
    from unittest.mock import patch

    db = str(tmp_path / "test.db")
    quiet = logging.getLogger("test_ingest_quiet")
    quiet.addHandler(logging.NullHandler())
    quiet.setLevel(logging.INFO)
    with get_poll_context(db) as ctx:
        with patch.object(ctx.health_store, "upsert_all", side_effect=RuntimeError("upsert failed")):
            with pytest.raises(RuntimeError, match="upsert failed"):
                run_one_cycle(ctx, [], log=quiet)
    assert ctx._closed
