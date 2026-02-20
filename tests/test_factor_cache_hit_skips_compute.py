"""Factor cache: cache hit skips OLS compute; no_cache/force/use_cache=False disable cache."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.factor_materialize import (
    FactorMaterializeConfig,
    materialize_factor_run,
)


def _make_returns(n_ts: int = 50, n_assets: int = 5, seed: int = 42) -> pd.DataFrame:
    import numpy as np

    np.random.seed(seed)
    idx = pd.date_range("2025-01-01", periods=n_ts, freq="h")
    cols = ["BTC_spot", "ETH_spot"] + [f"A{i}" for i in range(n_assets)]
    data = np.random.randn(n_ts, len(cols)) * 0.01
    return pd.DataFrame(data, index=idx, columns=cols)


@pytest.fixture
def db_with_factor_run():
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        run_migrations(conn, path)
        returns_df = _make_returns(80, 5)
        config = FactorMaterializeConfig(
            dataset_id="cache_ds",
            freq="1h",
            window_bars=24,
            min_obs=12,
            factors=["BTC_spot", "ETH_spot"],
        )
        run_id = materialize_factor_run(conn, returns_df, config, use_cache=False)
        cur = conn.execute("SELECT COUNT(*) FROM factor_betas WHERE factor_run_id = ?", (run_id,))
        beta_count = cur.fetchone()[0]
        cur = conn.execute("SELECT COUNT(*) FROM residual_returns WHERE factor_run_id = ?", (run_id,))
        resid_count = cur.fetchone()[0]
        conn.close()
        yield path, run_id, beta_count, resid_count, returns_df, config
    finally:
        Path(path).unlink(missing_ok=True)


def test_factor_cache_hit_skips_compute(db_with_factor_run):
    """When DB has matching factor_run and rowcounts, materialize with use_cache=True does not call OLS."""
    path, run_id, beta_count, resid_count, returns_df, config = db_with_factor_run
    from unittest.mock import patch

    from crypto_analyzer.factors import causal_rolling_ols as real_ols

    ols_calls = []

    def track_ols(*args, **kwargs):
        ols_calls.append(1)
        return real_ols(*args, **kwargs)

    with patch("crypto_analyzer.factor_materialize.causal_rolling_ols", side_effect=track_ols):
        with patch(
            "crypto_analyzer.factor_materialize.expected_factor_rowcounts_from_shape",
            return_value=(beta_count, resid_count),
        ):
            conn = sqlite3.connect(path)
            out_id = materialize_factor_run(conn, returns_df, config, use_cache=True)
            conn.close()
    assert out_id == run_id
    assert len(ols_calls) == 0


def test_factor_cache_disabled_by_env(db_with_factor_run):
    """CRYPTO_ANALYZER_NO_CACHE=1 causes recompute (OLS called)."""
    path, run_id, beta_count, resid_count, returns_df, config = db_with_factor_run
    from unittest.mock import patch

    from crypto_analyzer.factors import causal_rolling_ols as real_ols

    ols_calls = []

    def track_ols(*args, **kwargs):
        ols_calls.append(1)
        return real_ols(*args, **kwargs)

    with patch("crypto_analyzer.factor_materialize.causal_rolling_ols", side_effect=track_ols):
        with patch(
            "crypto_analyzer.factor_materialize.expected_factor_rowcounts_from_shape",
            return_value=(beta_count, resid_count),
        ):
            os.environ["CRYPTO_ANALYZER_NO_CACHE"] = "1"
            try:
                conn = sqlite3.connect(path)
                materialize_factor_run(conn, returns_df, config, use_cache=True)
                conn.close()
            finally:
                os.environ.pop("CRYPTO_ANALYZER_NO_CACHE", None)
    assert len(ols_calls) >= 1


def test_factor_cache_disabled_by_force(db_with_factor_run):
    """force=True causes recompute (OLS called)."""
    path, run_id, beta_count, resid_count, returns_df, config = db_with_factor_run
    from unittest.mock import patch

    from crypto_analyzer.factors import causal_rolling_ols as real_ols

    ols_calls = []

    def track_ols(*args, **kwargs):
        ols_calls.append(1)
        return real_ols(*args, **kwargs)

    with patch("crypto_analyzer.factor_materialize.causal_rolling_ols", side_effect=track_ols):
        with patch(
            "crypto_analyzer.factor_materialize.expected_factor_rowcounts_from_shape",
            return_value=(beta_count, resid_count),
        ):
            conn = sqlite3.connect(path)
            materialize_factor_run(conn, returns_df, config, use_cache=True, force=True)
            conn.close()
    assert len(ols_calls) >= 1


def test_factor_cache_disabled_by_use_cache_false(db_with_factor_run):
    """use_cache=False causes recompute (OLS called)."""
    path, run_id, beta_count, resid_count, returns_df, config = db_with_factor_run
    from unittest.mock import patch

    from crypto_analyzer.factors import causal_rolling_ols as real_ols

    ols_calls = []

    def track_ols(*args, **kwargs):
        ols_calls.append(1)
        return real_ols(*args, **kwargs)

    with patch("crypto_analyzer.factor_materialize.causal_rolling_ols", side_effect=track_ols):
        conn = sqlite3.connect(path)
        materialize_factor_run(conn, returns_df, config, use_cache=False)
        conn.close()
    assert len(ols_calls) >= 1
