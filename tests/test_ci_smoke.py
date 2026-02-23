"""CI smoke command: exits 0, no network, synthetic data."""

from __future__ import annotations

import os
import subprocess
import sys


def test_smoke_ci_exits_zero():
    """smoke --ci exits 0 and prints success summary (runs under CRYPTO_ANALYZER_NO_NETWORK=1)."""
    env = {**os.environ, "CRYPTO_ANALYZER_NO_NETWORK": "1"}
    r = subprocess.run(
        [sys.executable, "-m", "crypto_analyzer", "smoke", "--ci"],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    stderr = r.stderr or ""
    assert "Network access disabled" not in stderr, "Guard should not trigger; stderr: " + stderr
    out = (r.stdout or "") + stderr
    assert "dataset_id_v2" in out or "run_key" in out
    assert "CI smoke OK" in out or "OK" in out
