"""Regime materialize: idempotent, deterministic run_id, gated by flag."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.db.migrations_phase3 import run_migrations_phase3
from crypto_analyzer.regimes.regime_detector import RegimeStateSeries
from crypto_analyzer.regimes.regime_materialize import (
    RegimeMaterializeConfig,
    compute_regime_run_id,
    materialize_regime_run,
)


def _make_states(n: int = 10):
    ts = pd.date_range("2026-02-01", periods=n, freq="h")
    return RegimeStateSeries(
        ts_utc=pd.Series(ts),
        regime_label=pd.Series(["low_vol"] * n),
        regime_prob=pd.Series([0.9] * n),
    )


def test_compute_regime_run_id_deterministic():
    """Same config -> same regime_run_id."""
    cfg = RegimeMaterializeConfig(dataset_id="ds1", freq="1h", model="threshold_vol_v1")
    a = compute_regime_run_id(cfg)
    b = compute_regime_run_id(cfg)
    assert a == b
    assert a.startswith("rgm_")


def test_materialize_raises_when_regimes_disabled():
    """materialize_regime_run must raise when CRYPTO_ANALYZER_ENABLE_REGIMES is not set."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn0 = sqlite3.connect(path)
        run_migrations(conn0, path)
        conn0.close()
        conn1 = sqlite3.connect(path)
        run_migrations_phase3(conn1, path)
        conn1.close()
        conn = sqlite3.connect(path)
        try:
            with patch.dict(os.environ, {"CRYPTO_ANALYZER_ENABLE_REGIMES": "0"}, clear=False):
                with pytest.raises(RuntimeError, match="CRYPTO_ANALYZER_ENABLE_REGIMES"):
                    materialize_regime_run(
                        conn,
                        _make_states(5),
                        RegimeMaterializeConfig(dataset_id="ds1", freq="1h", model="threshold_vol_v1"),
                    )
        finally:
            conn.close()
    finally:
        Path(path).unlink(missing_ok=True)


def test_materialize_idempotent_and_deterministic_run_id():
    """With regimes enabled: same config -> same run_id; rerun -> same row count (replace)."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        run_migrations_phase3(conn, path)
        conn.close()

        with patch.dict(os.environ, {"CRYPTO_ANALYZER_ENABLE_REGIMES": "1"}, clear=False):
            conn = sqlite3.connect(path)
            try:
                cfg = RegimeMaterializeConfig(dataset_id="ds2", freq="1h", model="threshold_vol_v1")
                rid1 = materialize_regime_run(conn, _make_states(8), cfg, created_at_utc="2026-02-19T12:00:00Z")
                cur = conn.execute("SELECT COUNT(*) FROM regime_states WHERE regime_run_id = ?", (rid1,))
                count1 = cur.fetchone()[0]
                rid2 = materialize_regime_run(conn, _make_states(8), cfg, created_at_utc="2026-02-19T12:00:00Z")
                cur = conn.execute("SELECT COUNT(*) FROM regime_states WHERE regime_run_id = ?", (rid2,))
                count2 = cur.fetchone()[0]
                assert rid1 == rid2
                assert count1 == 8
                assert count2 == 8
            finally:
                conn.close()
    finally:
        Path(path).unlink(missing_ok=True)
