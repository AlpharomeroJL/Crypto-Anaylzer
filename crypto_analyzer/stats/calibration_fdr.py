"""FDR (BH/BY) calibration: smoke (fast) and full (slow) entrypoints."""

from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd

from crypto_analyzer.multiple_testing_adjuster import adjust
from crypto_analyzer.rng import rng_from_seed


def calibrate_fdr_smoke(
    n_rep: int = 30,
    n_hyp: int = 10,
    seed: int = 42,
) -> Dict[str, Any]:
    """Quick smoke: BH/BY on random p-values; assert non-degenerate (not all 0 or 1)."""
    rng = rng_from_seed(seed)
    p_vals_list = []
    adj_bh_list = []
    adj_by_list = []
    for _ in range(n_rep):
        p = rng.uniform(0.01, 0.99, size=n_hyp)
        p_ser = pd.Series(p)
        adj_bh, _ = adjust(p_ser, method="bh", q=0.05)
        adj_by, _ = adjust(p_ser, method="by", q=0.05)
        p_vals_list.append(p)
        adj_bh_list.append(adj_bh.values)
        adj_by_list.append(adj_by.values)
    adj_bh_arr = np.array(adj_bh_list)
    adj_by_arr = np.array(adj_by_list)
    return {
        "n_rep": n_rep,
        "n_hyp": n_hyp,
        "adj_bh_in_01": bool(np.all((adj_bh_arr >= 0) & (adj_bh_arr <= 1))),
        "adj_by_in_01": bool(np.all((adj_by_arr >= 0) & (adj_by_arr <= 1))),
        "not_all_zero": bool(np.any(adj_bh_arr != 0) and np.any(adj_by_arr != 0)),
        "not_all_one": bool(np.any(adj_bh_arr != 1) and np.any(adj_by_arr != 1)),
    }


def calibrate_fdr_full(
    n_rep: int = 500,
    n_hyp: int = 50,
    seed: int = 42,
) -> Dict[str, Any]:
    """Full calibration (mark with @pytest.mark.slow)."""
    return calibrate_fdr_smoke(n_rep=n_rep, n_hyp=n_hyp, seed=seed)
