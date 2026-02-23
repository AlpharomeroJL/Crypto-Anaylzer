"""Demo-lite: init + synthetic data + check-dataset, no network."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def test_demo_lite_init_then_demo_lite_then_check_dataset():
    """init -> demo-lite -> check-dataset with temp DB; exit 0 and dataset_id_v2 in output."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "demo.sqlite")
        root = Path(__file__).resolve().parent.parent
        env = {**os.environ, "CRYPTO_ANALYZER_NO_NETWORK": "1"}
        r1 = subprocess.run(
            [sys.executable, "-m", "crypto_analyzer", "init", "--db", db],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(root),
            env=env,
        )
        assert r1.returncode == 0, (r1.stdout or "") + (r1.stderr or "")
        r2 = subprocess.run(
            [sys.executable, "-m", "crypto_analyzer", "demo-lite", "--db", db],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(root),
            env=env,
        )
        assert r2.returncode == 0, (r2.stdout or "") + (r2.stderr or "")
        assert "Network access disabled" not in (r2.stderr or "")
        r3 = subprocess.run(
            [sys.executable, "-m", "crypto_analyzer", "check-dataset", "--db", db],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(root),
            env=env,
        )
        assert r3.returncode == 0, (r3.stdout or "") + (r3.stderr or "")
        out = (r3.stdout or "") + (r3.stderr or "")
        assert "dataset_id_v2" in out
