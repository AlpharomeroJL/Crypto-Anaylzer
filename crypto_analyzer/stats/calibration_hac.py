"""HAC calibration: optional skeleton; smoke (fast) and full (slow) entrypoints."""

from __future__ import annotations

from typing import Any, Dict


def calibrate_hac_smoke(
    n_rep: int = 20,
    seed: int = 42,
) -> Dict[str, Any]:
    """Quick smoke: placeholder; no HAC implementation in this skeleton."""
    return {
        "n_rep": n_rep,
        "skipped": True,
        "reason": "HAC calibration skeleton only",
    }


def calibrate_hac_full(
    n_rep: int = 200,
    seed: int = 42,
) -> Dict[str, Any]:
    """Full calibration (mark with @pytest.mark.slow)."""
    return calibrate_hac_smoke(n_rep=n_rep, seed=seed)
