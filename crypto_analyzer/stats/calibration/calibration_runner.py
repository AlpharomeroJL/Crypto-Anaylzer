"""Calibration runner: run a single trial or batch with a DGP and evaluator."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

import numpy as np

from crypto_analyzer.rng import rng_from_seed


def run_calibration_trial(
    generator: Callable[..., np.ndarray],
    evaluator: Callable[[np.ndarray], Dict[str, Any]],
    seed: Optional[int] = None,
    rng: Optional[np.random.Generator] = None,
    **gen_kw: Any,
) -> Dict[str, Any]:
    """
    Run one calibration trial: generate data with generator(**gen_kw, seed=..., rng=...), evaluate.
    Returns evaluator output plus optional seed/trial_id.
    """
    if rng is None:
        rng = rng_from_seed(seed)
    per_seed = int(rng.integers(0, 2**63 - 1))
    data = generator(**gen_kw, seed=per_seed, rng=None)
    out = evaluator(data)
    out["_trial_seed"] = per_seed
    return out


def run_calibration_batch(
    generator: Callable[..., np.ndarray],
    evaluator: Callable[[np.ndarray], Dict[str, Any]],
    n_trials: int,
    seed: Optional[int] = None,
    run_key: str = "",
    **gen_kw: Any,
) -> Dict[str, Any]:
    """
    Run n_trials; collect results. If run_key provided, use central rng_for for reproducibility.
    """
    from crypto_analyzer.rng import SALT_CALIBRATION, rng_for, rng_from_seed

    if run_key:
        rng = rng_for(run_key, SALT_CALIBRATION)
    else:
        rng = rng_from_seed(seed)
    results = []
    for _ in range(n_trials):
        res = run_calibration_trial(generator, evaluator, seed=None, rng=rng, **gen_kw)
        results.append(res)
    return {"n_trials": n_trials, "results": results}
