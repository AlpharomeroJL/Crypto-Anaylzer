"""
Synthetic data generators and runner for null/calibration experiments.
All randomness via explicit seed or np.random.Generator from central rng module.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

import numpy as np

from .rng import rng_from_seed


def gen_iid(
    n: int,
    k: int,
    seed: Optional[int] = None,
    rng: Optional[np.random.Generator] = None,
) -> np.ndarray:
    """IID Gaussian (n times, k series). Shape (n, k)."""
    if rng is None:
        rng = rng_from_seed(seed)
    return rng.standard_normal((n, k))


def gen_ar1(
    n: int,
    k: int,
    phi: float,
    seed: Optional[int] = None,
    rng: Optional[np.random.Generator] = None,
) -> np.ndarray:
    """AR(1) with coefficient phi. Shape (n, k)."""
    if rng is None:
        rng = rng_from_seed(seed)
    out = np.zeros((n, k))
    out[0] = rng.standard_normal(k)
    for t in range(1, n):
        out[t] = phi * out[t - 1] + rng.standard_normal(k)
    return out


def gen_correlated(
    n: int,
    k: int,
    rho: float,
    seed: Optional[int] = None,
    rng: Optional[np.random.Generator] = None,
) -> np.ndarray:
    """Cross-sectional correlation rho. Shape (n, k)."""
    if rng is None:
        rng = rng_from_seed(seed)
    z = rng.standard_normal((n, 1))
    e = rng.standard_normal((n, k))
    return np.sqrt(rho) * z + np.sqrt(1 - rho) * e


def gen_mean_shift(
    n: int,
    k: int,
    shift_at: int,
    delta: float,
    seed: Optional[int] = None,
    rng: Optional[np.random.Generator] = None,
) -> np.ndarray:
    """Regime shift: mean +delta after index shift_at. Shape (n, k)."""
    if rng is None:
        rng = rng_from_seed(seed)
    x = rng.standard_normal((n, k))
    x[shift_at:] += delta
    return x


def run_null_experiment(
    generator_fn: Callable[..., np.ndarray],
    evaluator_fn: Callable[[np.ndarray], Any],
    n_rep: int,
    seed: Optional[int] = None,
    rng: Optional[np.random.Generator] = None,
    **gen_kw: Any,
) -> Dict[str, Any]:
    """
    Run generator n_rep times, evaluate each; return summary dict.
    generator_fn is called with **gen_kw and must accept seed= and rng=;
    we pass per-rep seed or spawned rng. evaluator_fn(data) returns a scalar or dict.
    """
    if rng is None:
        rng = rng_from_seed(seed)
    results = []
    for i in range(n_rep):
        per_seed = int(rng.integers(0, 2**63 - 1))
        data = generator_fn(**gen_kw, seed=per_seed, rng=None)
        out = evaluator_fn(data)
        if isinstance(out, dict):
            results.append(out)
        else:
            results.append({"value": out})
    return {"n_rep": n_rep, "results": results}
