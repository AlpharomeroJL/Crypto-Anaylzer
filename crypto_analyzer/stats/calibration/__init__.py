"""Calibration harness: runner, null DGP, metrics, configs. Two-tier: fast CI / slow marker."""

from __future__ import annotations

from .calibration_runner import run_calibration_batch, run_calibration_trial
from .configs import CalibrationConfig
from .metrics import type_i_error_summary
from .null_dgp import gen_iid_pvalues, gen_null_ic_series

__all__ = [
    "CalibrationConfig",
    "type_i_error_summary",
    "gen_iid_pvalues",
    "gen_null_ic_series",
    "run_calibration_trial",
    "run_calibration_batch",
]
