"""Calibration metrics: Type I error, FDR, FWER summaries."""

from __future__ import annotations

from typing import Any, Dict, List


def type_i_error_summary(
    rejections: List[bool],
    nominal_alpha: float = 0.05,
) -> Dict[str, Any]:
    """
    Summary for Type I error calibration.
    rejections: list of bool (True = rejected) per trial.
    Returns empirical rate, nominal, and a simple pass flag (empirical not >> nominal).
    """
    n = len(rejections)
    if n == 0:
        return {"empirical_rate": 0.0, "nominal_alpha": nominal_alpha, "n_trials": 0}
    emp = sum(rejections) / n
    return {
        "empirical_rate": emp,
        "nominal_alpha": nominal_alpha,
        "n_trials": n,
        "within_tolerance": emp <= nominal_alpha + 0.10,
    }


def fdr_summary(
    n_discoveries: List[int],
    n_true_positives: List[int],
    q: float = 0.05,
) -> Dict[str, Any]:
    """FDR summary: list of (discoveries, true_positives) per trial."""
    n = len(n_discoveries)
    if n == 0:
        return {"empirical_fdr": 0.0, "q": q, "n_trials": 0}
    fdr_list = []
    for d, tp in zip(n_discoveries, n_true_positives):
        if d == 0:
            fdr_list.append(0.0)
        else:
            fp = d - tp
            fdr_list.append(fp / d)
    emp_fdr = sum(fdr_list) / n
    return {
        "empirical_fdr": emp_fdr,
        "q": q,
        "n_trials": n,
        "within_tolerance": emp_fdr <= q + 0.10,
    }
