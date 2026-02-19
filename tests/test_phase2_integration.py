"""Phase 2 end-to-end: migrations -> factor materialization -> registry -> null suite -> artifacts."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.experiments import record_experiment_run
from crypto_analyzer.factor_materialize import (
    FactorMaterializeConfig,
    materialize_factor_run,
)
from crypto_analyzer.null_suite import run_null_suite, write_null_suite_artifacts


def test_phase2_e2e_migrations_factor_registry_null_artifacts(tmp_path: Path):
    """E2E: temp DB -> migrations -> factor run -> experiment row -> null suite -> artifacts."""
    tmp = str(tmp_path)
    db_path = Path(tmp) / "phase2_e2e.sqlite"
    conn = sqlite3.connect(str(db_path))
    run_migrations(conn, str(db_path))
    # Check schema_migrations and factor tables exist
    cur = conn.execute("SELECT COUNT(*) FROM schema_migrations")
    assert cur.fetchone()[0] >= 1
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('factor_model_runs','factor_betas','residual_returns')"
    )
    assert len(cur.fetchall()) == 3
    # Small returns fixture
    np.random.seed(42)
    n_ts, n_assets = 40, 6
    idx = pd.date_range("2025-01-01", periods=n_ts, freq="h")
    cols = ["BTC_spot", "ETH_spot"] + [f"A{i}" for i in range(n_assets - 2)]
    returns_df = pd.DataFrame(np.random.randn(n_ts, n_assets) * 0.01, index=idx, columns=cols)
    config = FactorMaterializeConfig(
        dataset_id="e2e_ds",
        freq="1h",
        window_bars=20,
        min_obs=10,
        factors=["BTC_spot", "ETH_spot"],
    )
    factor_run_id = materialize_factor_run(conn, returns_df, config)
    assert factor_run_id.startswith("fctr_")
    cur = conn.execute(
        "SELECT COUNT(*) FROM factor_model_runs WHERE factor_run_id = ?",
        (factor_run_id,),
    )
    assert cur.fetchone()[0] == 1
    conn.close()
    # Experiment registry (separate experiment DB)
    exp_db = Path(tmp) / "experiments.db"
    record_experiment_run(
        db_path=str(exp_db),
        experiment_row={
            "run_id": "phase2_e2e_run",
            "ts_utc": "2026-02-19T12:00:00Z",
            "dataset_id": "e2e_ds",
        },
        metrics_dict={"mean_ic": 0.01},
    )
    assert exp_db.is_file()
    # Null suite on small fixture
    signal_df = returns_df[[c for c in returns_df.columns if c not in ("BTC_spot", "ETH_spot")]].copy()
    result = run_null_suite(signal_df, returns_df, n_sim=5, block_size=4, seed=7)
    out_dir = Path(tmp) / "null_out"
    paths = write_null_suite_artifacts(result, out_dir)
    assert len(paths) >= 2
    for p in paths:
        assert Path(p).is_file()
