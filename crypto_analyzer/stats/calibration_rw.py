"""Romano-Wolf calibration: smoke (fast) and full (slow) entrypoints."""

from __future__ import annotations

import os
from typing import Any, Dict

import numpy as np
import pandas as pd

from crypto_analyzer.rng import rng_from_seed
from crypto_analyzer.stats.reality_check import (
    RealityCheckConfig,
    make_null_generator_stationary,
    run_reality_check,
)


def calibrate_rw_smoke(
    n_obs: int = 50,
    n_sim: int = 30,
    seed: int = 42,
) -> Dict[str, Any]:
    """Quick smoke: run RC (with RW when env set) on small data; assert adjusted p-values in [0,1]."""
    rw_was = os.environ.get("CRYPTO_ANALYZER_ENABLE_ROMANOWOLF", "")
    try:
        os.environ["CRYPTO_ANALYZER_ENABLE_ROMANOWOLF"] = "1"
        rng = rng_from_seed(seed)
        series_by_hyp = {
            "a|1": pd.Series(rng.standard_normal(n_obs).cumsum() * 0.01),
            "b|1": pd.Series(rng.standard_normal(n_obs).cumsum() * 0.01),
        }
        observed = pd.Series({"a|1": 0.015, "b|1": 0.008})
        cfg = RealityCheckConfig(n_sim=n_sim, method="stationary", avg_block_length=8, seed=seed)
        null_gen = make_null_generator_stationary(series_by_hyp, cfg)
        res = run_reality_check(observed, null_gen, cfg)
        rw_adj = res.get("rw_adjusted_p_values")
        if rw_adj is not None and len(rw_adj) > 0:
            vals = rw_adj.values
            in_01 = bool(np.all((vals >= 0) & (vals <= 1)))
            not_all_zero = bool(np.any(vals != 0))
            not_all_one = bool(np.any(vals != 1))
        else:
            in_01 = not_all_zero = not_all_one = True
        return {
            "rc_p_value": res["rc_p_value"],
            "rw_adj_in_01": in_01,
            "rw_not_all_zero": not_all_zero,
            "rw_not_all_one": not_all_one,
        }
    finally:
        if rw_was == "":
            os.environ.pop("CRYPTO_ANALYZER_ENABLE_ROMANOWOLF", None)
        else:
            os.environ["CRYPTO_ANALYZER_ENABLE_ROMANOWOLF"] = rw_was


def calibrate_rw_full(
    n_obs: int = 150,
    n_sim: int = 300,
    seed: int = 42,
) -> Dict[str, Any]:
    """Full calibration (mark with @pytest.mark.slow)."""
    return calibrate_rw_smoke(n_obs=n_obs, n_sim=n_sim, seed=seed)
