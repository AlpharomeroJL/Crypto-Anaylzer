"""Null data-generating processes for calibration (Type I, FDR, RC, RW)."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from crypto_analyzer.rng import rng_from_seed


def gen_iid_pvalues(
    n: int,
    seed: Optional[int] = None,
    rng: Optional[np.random.Generator] = None,
) -> np.ndarray:
    """IID uniform p-values under null. Shape (n,)."""
    if rng is None:
        rng = rng_from_seed(seed)
    return rng.uniform(0.001, 0.999, size=n)


def gen_null_ic_series(
    n_obs: int,
    n_series: int = 2,
    seed: Optional[int] = None,
    rng: Optional[np.random.Generator] = None,
) -> dict[str, pd.Series]:
    """Synthetic null IC-like series (no edge). Returns dict hypothesis_id -> Series."""
    if rng is None:
        rng = rng_from_seed(seed)
    idx = pd.RangeIndex(0, n_obs)
    out = {}
    for i in range(n_series):
        out[f"h{i}|1"] = pd.Series(rng.standard_normal(n_obs).cumsum() * 0.01, index=idx)
    return out
