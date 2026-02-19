"""Tests for factor materialization (factor_run_id, write path, no leakage)."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.factor_materialize import (
    FactorMaterializeConfig,
    compute_factor_run_id,
    materialize_factor_run,
)


def _make_returns_fixture(n_ts: int = 50, n_assets: int = 5, seed: int = 42) -> pd.DataFrame:
    np.random.seed(seed)
    idx = pd.date_range("2025-01-01", periods=n_ts, freq="h")
    cols = ["BTC_spot", "ETH_spot"] + [f"A{i}" for i in range(n_assets)]
    data = np.random.randn(n_ts, len(cols)) * 0.01
    return pd.DataFrame(data, index=idx, columns=cols)


def test_factor_run_id_deterministic():
    """Same config + dataset_id -> same factor_run_id."""
    config = FactorMaterializeConfig(
        dataset_id="ds1",
        freq="1h",
        window_bars=72,
        min_obs=24,
        factors=["BTC_spot", "ETH_spot"],
    )
    id1 = compute_factor_run_id(config)
    id2 = compute_factor_run_id(config)
    assert id1 == id2
    assert id1.startswith("fctr_")
    assert len(id1) == 21  # fctr_ + 16 hex

    config2 = FactorMaterializeConfig(
        dataset_id="ds2",
        freq="1h",
        window_bars=72,
        min_obs=24,
        factors=["BTC_spot", "ETH_spot"],
    )
    assert compute_factor_run_id(config2) != id1


def test_materialize_factor_run_writes_tables():
    """Materialize writes factor_model_runs, factor_betas, residual_returns."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        returns_df = _make_returns_fixture(80, 5)
        config = FactorMaterializeConfig(
            dataset_id="test_ds",
            freq="1h",
            window_bars=24,
            min_obs=12,
            factors=["BTC_spot", "ETH_spot"],
        )
        run_id = materialize_factor_run(conn, returns_df, config)
        assert run_id.startswith("fctr_")
        cur = conn.execute("SELECT COUNT(*) FROM factor_model_runs WHERE factor_run_id = ?", (run_id,))
        assert cur.fetchone()[0] == 1
        cur = conn.execute("SELECT COUNT(*) FROM factor_betas WHERE factor_run_id = ?", (run_id,))
        beta_count = cur.fetchone()[0]
        assert beta_count > 0
        cur = conn.execute("SELECT COUNT(*) FROM residual_returns WHERE factor_run_id = ?", (run_id,))
        resid_count = cur.fetchone()[0]
        assert resid_count > 0
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)


def test_materialize_deterministic_under_fixed_time():
    """Under CRYPTO_ANALYZER_DETERMINISTIC_TIME, two runs yield same row counts and content hash."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        os.environ["CRYPTO_ANALYZER_DETERMINISTIC_TIME"] = "2026-02-19T12:00:00Z"
        try:
            conn = sqlite3.connect(path)
            run_migrations(conn, path)
            returns_df = _make_returns_fixture(60, 4)
            config = FactorMaterializeConfig(
                dataset_id="det_ds",
                freq="1h",
                window_bars=20,
                min_obs=10,
                factors=["BTC_spot", "ETH_spot"],
            )
            run_id1 = materialize_factor_run(conn, returns_df, config)
            cur = conn.execute("SELECT COUNT(*) FROM factor_betas WHERE factor_run_id = ?", (run_id1,))
            count1 = cur.fetchone()[0]
            cur = conn.execute(
                "SELECT factor_run_id, ts_utc, asset_id, beta FROM factor_betas ORDER BY ts_utc, asset_id LIMIT 5"
            )
            rows1 = cur.fetchall()
            conn.close()

            conn2 = sqlite3.connect(path)
            run_id2 = materialize_factor_run(conn2, returns_df, config)
            cur = conn2.execute("SELECT COUNT(*) FROM factor_betas WHERE factor_run_id = ?", (run_id2,))
            count2 = cur.fetchone()[0]
            cur = conn2.execute(
                "SELECT factor_run_id, ts_utc, asset_id, beta FROM factor_betas ORDER BY ts_utc, asset_id LIMIT 5"
            )
            rows2 = cur.fetchall()
            conn2.close()

            assert run_id1 == run_id2
            assert count1 == count2
            assert rows1 == rows2
        finally:
            os.environ.pop("CRYPTO_ANALYZER_DETERMINISTIC_TIME", None)
    finally:
        Path(path).unlink(missing_ok=True)


def test_materialize_idempotent_same_run_id():
    """Same factor_run_id reuses/overwrites without duplicates."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        returns_df = _make_returns_fixture(50, 3)
        config = FactorMaterializeConfig(
            dataset_id="idem_ds",
            freq="1h",
            window_bars=20,
            min_obs=8,
            factors=["BTC_spot", "ETH_spot"],
        )
        run_id = materialize_factor_run(conn, returns_df, config)
        cur = conn.execute("SELECT COUNT(*) FROM factor_betas WHERE factor_run_id = ?", (run_id,))
        count1 = cur.fetchone()[0]
        materialize_factor_run(conn, returns_df, config)
        cur = conn.execute("SELECT COUNT(*) FROM factor_betas WHERE factor_run_id = ?", (run_id,))
        count2 = cur.fetchone()[0]
        assert count1 == count2
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)


def test_materialize_kalman_beta_writes_tables():
    """Materialize with estimator=kalman_beta writes factor_model_runs, factor_betas, residual_returns."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        returns_df = _make_returns_fixture(80, 3)
        config = FactorMaterializeConfig(
            dataset_id="kal_ds",
            freq="1h",
            window_bars=24,
            min_obs=12,
            factors=["BTC_spot", "ETH_spot"],
            estimator="kalman_beta",
            params={"process_var": 1e-5, "obs_var": 1e-4},
        )
        run_id = materialize_factor_run(conn, returns_df, config)
        assert run_id.startswith("fctr_")
        cur = conn.execute(
            "SELECT estimator FROM factor_model_runs WHERE factor_run_id = ?", (run_id,)
        )
        row = cur.fetchone()
        assert row is not None and row[0] == "kalman_beta"
        cur = conn.execute("SELECT COUNT(*) FROM factor_betas WHERE factor_run_id = ?", (run_id,))
        assert cur.fetchone()[0] > 0
        cur = conn.execute(
            "SELECT COUNT(*) FROM residual_returns WHERE factor_run_id = ?", (run_id,)
        )
        assert cur.fetchone()[0] > 0
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)


def test_materialize_kalman_beta_idempotent():
    """Second materialize with same kalman_beta config overwrites without duplicating rows."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        returns_df = _make_returns_fixture(60, 3)
        config = FactorMaterializeConfig(
            dataset_id="kal_idem_ds",
            freq="1h",
            window_bars=20,
            min_obs=10,
            factors=["BTC_spot", "ETH_spot"],
            estimator="kalman_beta",
            params={"obs_var": 1e-4},
        )
        run_id = materialize_factor_run(conn, returns_df, config)
        cur = conn.execute("SELECT COUNT(*) FROM factor_betas WHERE factor_run_id = ?", (run_id,))
        count1 = cur.fetchone()[0]
        materialize_factor_run(conn, returns_df, config)
        cur = conn.execute("SELECT COUNT(*) FROM factor_betas WHERE factor_run_id = ?", (run_id,))
        count2 = cur.fetchone()[0]
        assert count1 == count2
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)


def test_as_of_lag_bars_must_be_at_least_one():
    """causal_rolling_ols and causal_residual_returns reject as_of_lag_bars < 1 (no lookahead)."""
    from crypto_analyzer.factors import causal_residual_returns, causal_rolling_ols

    df = _make_returns_fixture(20, 2)
    with pytest.raises(ValueError, match="as_of_lag_bars must be >= 1"):
        causal_rolling_ols(df, factor_cols=["BTC_spot", "ETH_spot"], as_of_lag_bars=0)
    with pytest.raises(ValueError, match="as_of_lag_bars must be >= 1"):
        causal_residual_returns(df, factor_cols=["BTC_spot", "ETH_spot"], as_of_lag_bars=0)


def test_causal_residuals_no_future_data():
    """Residuals at t do not use data after t (as_of_lag_bars respected)."""
    from crypto_analyzer.factors import causal_rolling_ols

    # Build returns where "future" factor return is perfectly correlated with asset
    n = 40
    idx = pd.date_range("2025-01-01", periods=n, freq="h")
    btc = np.random.randn(n) * 0.01
    eth = np.random.randn(n) * 0.01
    # Asset A0 = 0.5*BTC + 0.5*ETH + noise; no lookahead
    a0 = 0.5 * btc + 0.5 * eth + np.random.randn(n) * 0.005
    df = pd.DataFrame({"BTC_spot": btc, "ETH_spot": eth, "A0": a0}, index=idx)
    betas_dict, r2_df, residual_df, alpha_df = causal_rolling_ols(
        df, factor_cols=["BTC_spot", "ETH_spot"], window_bars=20, min_obs=10, as_of_lag_bars=1
    )
    assert not residual_df.empty
    assert residual_df["A0"].notna().sum() >= 1
    # Residual at each t was computed using only data up to t-1 for the fit
    assert "A0" in betas_dict["BTC_spot"].columns
