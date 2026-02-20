"""Regime cache: cache hit skips write path; no_cache/force/use_cache=False disable cache."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.db.migrations_phase3 import run_migrations_phase3
from crypto_analyzer.regimes.regime_detector import RegimeStateSeries
from crypto_analyzer.regimes.regime_materialize import (
    RegimeMaterializeConfig,
    materialize_regime_run,
)


def _make_states(n: int):
    idx = pd.date_range("2025-01-01", periods=n, freq="h")
    return RegimeStateSeries(
        ts_utc=idx,
        regime_label=pd.Series(["low"] * n, index=idx),
        regime_prob=pd.Series([1.0] * n, index=idx),
    )


class _CountingConn:
    """Wraps a sqlite3.Connection and counts DELETE FROM regime_states calls."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self.delete_calls = 0

    def execute(self, sql, parameters=()):
        if "DELETE FROM regime_states" in (sql if isinstance(sql, str) else ""):
            self.delete_calls += 1
        return self._conn.execute(sql, parameters)

    def commit(self):
        return self._conn.commit()

    def close(self):
        return self._conn.close()


@pytest.fixture
def db_with_regime_run():
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        run_migrations_phase3(conn, path)
        config = RegimeMaterializeConfig(
            dataset_id="cache_ds",
            freq="1h",
            model="threshold_vol_v1",
        )
        states = _make_states(20)
        run_id = materialize_regime_run(conn, states, config, use_cache=False)
        cur = conn.execute("SELECT COUNT(*) FROM regime_states WHERE regime_run_id = ?", (run_id,))
        count = cur.fetchone()[0]
        conn.close()
        yield path, run_id, count, states, config
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass


@pytest.mark.skipif(
    os.environ.get("CRYPTO_ANALYZER_ENABLE_REGIMES") != "1",
    reason="Regime materialization requires CRYPTO_ANALYZER_ENABLE_REGIMES=1",
)
def test_regime_cache_hit_skips_compute(db_with_regime_run):
    """When DB has matching regime_run and state count, materialize with use_cache=True does not write."""
    path, run_id, state_count, states, config = db_with_regime_run
    conn = sqlite3.connect(path)
    wrapped = _CountingConn(conn)
    out_id = materialize_regime_run(wrapped, states, config, use_cache=True)
    wrapped.close()
    assert out_id == run_id
    assert wrapped.delete_calls == 0


@pytest.mark.skipif(
    os.environ.get("CRYPTO_ANALYZER_ENABLE_REGIMES") != "1",
    reason="Regime materialization requires CRYPTO_ANALYZER_ENABLE_REGIMES=1",
)
def test_regime_cache_disabled_by_env(db_with_regime_run):
    """CRYPTO_ANALYZER_NO_CACHE=1 causes write path (DELETE executed)."""
    path, run_id, state_count, states, config = db_with_regime_run
    conn = sqlite3.connect(path)
    wrapped = _CountingConn(conn)
    os.environ["CRYPTO_ANALYZER_NO_CACHE"] = "1"
    try:
        materialize_regime_run(wrapped, states, config, use_cache=True)
    finally:
        os.environ.pop("CRYPTO_ANALYZER_NO_CACHE", None)
    wrapped.close()
    assert wrapped.delete_calls >= 1


@pytest.mark.skipif(
    os.environ.get("CRYPTO_ANALYZER_ENABLE_REGIMES") != "1",
    reason="Regime materialization requires CRYPTO_ANALYZER_ENABLE_REGIMES=1",
)
def test_regime_cache_disabled_by_force(db_with_regime_run):
    """force=True causes write path."""
    path, run_id, state_count, states, config = db_with_regime_run
    conn = sqlite3.connect(path)
    wrapped = _CountingConn(conn)
    materialize_regime_run(wrapped, states, config, use_cache=True, force=True)
    wrapped.close()
    assert wrapped.delete_calls >= 1
