"""Reality Check calibration: smoke (fast) and full (slow) entrypoints."""

from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd

from crypto_analyzer.rng import rng_from_seed
from crypto_analyzer.stats.reality_check import (
    RealityCheckConfig,
    make_null_generator_stationary,
    run_reality_check,
)


def calibrate_rc_smoke(
    n_obs: int = 60,
    n_sim: int = 25,
    seed: int = 42,
) -> Dict[str, Any]:
    """Quick smoke: run RC on small synthetic IC series; assert p-value in [0,1], not degenerate."""
    rng = rng_from_seed(seed)
    series_by_hyp = {
        "a|1": pd.Series(rng.standard_normal(n_obs).cumsum() * 0.01),
        "b|1": pd.Series(rng.standard_normal(n_obs).cumsum() * 0.01),
    }
    observed = pd.Series({"a|1": 0.02, "b|1": 0.01})
    cfg = RealityCheckConfig(n_sim=n_sim, method="stationary", avg_block_length=8, seed=seed)
    null_gen = make_null_generator_stationary(series_by_hyp, cfg)
    res = run_reality_check(observed, null_gen, cfg)
    rc_p = res["rc_p_value"]
    null_max = res["null_max_distribution"]
    return {
        "rc_p_value": rc_p,
        "in_01": 0 <= rc_p <= 1,
        "not_degenerate": len(null_max) == n_sim and np.all(np.isfinite(null_max)),
        "actual_n_sim": res["actual_n_sim"],
    }


def calibrate_rc_full(
    n_obs: int = 200,
    n_sim: int = 500,
    seed: int = 42,
) -> Dict[str, Any]:
    """Full calibration (mark with @pytest.mark.slow)."""
    return calibrate_rc_smoke(n_obs=n_obs, n_sim=n_sim, seed=seed)
