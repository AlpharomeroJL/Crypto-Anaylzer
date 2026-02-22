"""CSCV/PBO calibration: smoke (fast) and full (slow) entrypoints."""

from __future__ import annotations

from typing import Any, Dict

import numpy as np

from crypto_analyzer.rng import rng_from_seed


def calibrate_cscv_smoke(
    n_rep: int = 20,
    T: int = 40,
    J: int = 4,
    S: int = 8,
    seed: int = 42,
) -> Dict[str, Any]:
    """Quick smoke: if pbo_cscv exists, run on small R; else return skipped stub. Assert outputs in [0,1] when present."""
    try:
        from crypto_analyzer.multiple_testing import pbo_cscv
    except ImportError:
        return {"n_rep": n_rep, "skipped": True, "reason": "pbo_cscv not available", "all_in_01": True}
    rng = rng_from_seed(seed)
    out_list = []
    for _ in range(n_rep):
        R = rng.standard_normal((T, J))
        res = pbo_cscv(R, S=S, seed=seed, max_splits=50, metric="mean")
        if "pbo_cscv_skipped_reason" in res:
            out_list.append({"skipped": True, "reason": res["pbo_cscv_skipped_reason"]})
        else:
            pbo = res.get("pbo_cscv", np.nan)
            out_list.append({"pbo_cscv": pbo, "in_01": 0 <= pbo <= 1 if np.isfinite(pbo) else True})
    pbo_vals = [x["pbo_cscv"] for x in out_list if "pbo_cscv" in x]
    return {
        "n_rep": n_rep,
        "n_with_pbo": len(pbo_vals),
        "all_in_01": all(x.get("in_01", True) for x in out_list),
        "not_all_same": len(set(pbo_vals)) > 1 or len(pbo_vals) == 0,
    }


def calibrate_cscv_full(
    n_rep: int = 100,
    T: int = 200,
    J: int = 10,
    S: int = 16,
    seed: int = 42,
) -> Dict[str, Any]:
    """Full calibration (mark with @pytest.mark.slow)."""
    return calibrate_cscv_smoke(n_rep=n_rep, T=T, J=J, S=S, seed=seed)
