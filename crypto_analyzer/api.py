"""
Read-only REST research API using FastAPI. No secrets, no auth.
Research-only; no execution.
"""
from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, List

from . import __version__

try:
    from fastapi import FastAPI, HTTPException
except ImportError:  # pragma: no cover
    FastAPI = None  # type: ignore[assignment,misc]

if FastAPI is not None:
    app = FastAPI(title="Crypto Analyzer Research API", version=__version__)
else:
    app = None  # type: ignore[assignment]


def _db_path() -> str:
    try:
        from . import config
        return config.db_path()
    except Exception:
        return "dex_data.sqlite"


def _experiment_db() -> str:
    return os.environ.get("EXPERIMENT_DB_PATH", "reports/experiments.db")


if app is not None:

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/latest/allowlist")
    def latest_allowlist() -> List[Dict[str, Any]]:
        db = _db_path()
        if not os.path.isfile(db):
            raise HTTPException(404, detail="Database file not found")
        try:
            with sqlite3.connect(db) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT * FROM universe_allowlist").fetchall()
        except sqlite3.OperationalError:
            raise HTTPException(404, detail="universe_allowlist table not found")
        if not rows:
            raise HTTPException(404, detail="Allowlist is empty")
        return [dict(r) for r in rows]

    @app.get("/experiments/recent")
    def experiments_recent(limit: int = 20) -> List[Dict[str, Any]]:
        from . import experiments as exp

        db = _experiment_db()
        df = exp.load_experiments(db, limit=limit)
        return df.to_dict(orient="records") if not df.empty else []

    @app.get("/experiments/{run_id}")
    def experiment_detail(run_id: str) -> Dict[str, Any]:
        from . import experiments as exp

        db = _experiment_db()
        df = exp.load_experiments(db, limit=10_000)
        if df.empty or run_id not in df["run_id"].values:
            raise HTTPException(404, detail=f"Experiment {run_id} not found")
        row = df[df["run_id"] == run_id].iloc[0].to_dict()
        metrics_df = exp.load_experiment_metrics(db, run_id)
        row["metrics"] = metrics_df.to_dict(orient="records") if not metrics_df.empty else []
        return row

    @app.get("/metrics/{name}/history")
    def metric_history(name: str, limit: int = 100) -> List[Dict[str, Any]]:
        from . import experiments as exp

        db = _experiment_db()
        df = exp.load_metric_history(db, name, limit=limit)
        return df.to_dict(orient="records") if not df.empty else []

    @app.get("/reports/latest")
    def reports_latest() -> Dict[str, str]:
        from .governance import load_manifests

        df = load_manifests("reports")
        if df.empty:
            raise HTTPException(404, detail="No report manifests found")
        latest = df.iloc[-1]
        return {
            "report_dir": "reports",
            "manifest_id": str(latest.get("run_id", "")),
            "manifest_path": str(latest.get("path", "")),
        }
