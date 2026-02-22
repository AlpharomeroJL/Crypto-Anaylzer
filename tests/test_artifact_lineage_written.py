"""Phase 3 A4: Pipeline run with conn writes expected artifact lineage rows."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.db.migrations_phase3 import run_migrations_phase3
from crypto_analyzer.pipelines.research_pipeline import run_research_pipeline


def test_pipeline_with_conn_writes_artifact_lineage():
    config = {
        "out_dir": "artifacts/research",
        "dataset_id": "demo",
        "signal_name": "momentum_24h",
        "freq": "1h",
        "horizons": [1, 4],
        "seed": 42,
        "n_bars": 100,
        "n_assets": 3,
    }
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        out.mkdir()
        config["out_dir"] = str(out)
        db_path = Path(tmp) / "phase3.db"
        conn = sqlite3.connect(str(db_path))
        run_migrations(conn, str(db_path))
        run_migrations_phase3(conn, str(db_path))
        result = run_research_pipeline(
            config,
            hypothesis_id="h1",
            family_id="f1",
            conn=conn,
        )
        conn.close()
        assert result.bundle_dir
        conn2 = sqlite3.connect(str(db_path))
        cur = conn2.execute("SELECT COUNT(*) FROM artifact_lineage WHERE run_instance_id = ?", (result.run_id,))
        n = cur.fetchone()[0]
        conn2.close()
        assert n >= 1, "at least one artifact_lineage row should be written when conn provided and tables exist"
