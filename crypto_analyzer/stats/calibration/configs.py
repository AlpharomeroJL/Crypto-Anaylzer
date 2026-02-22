"""Calibration run configs: fast (CI) vs slow (nightly/manual)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from crypto_analyzer.contracts.schema_versions import CALIBRATION_HARNESS_SCHEMA_VERSION


@dataclass
class CalibrationConfig:
    """Config for calibration runs. Fast: small n_trials, wide tolerances."""

    n_trials: int = 50
    n_obs: int = 80
    n_hyp: int = 10
    seed: Optional[int] = 42
    run_key: str = ""
    # Tolerances for Type I / FDR (wide for fast CI)
    fdr_tolerance: float = 0.10
    rc_pvalue_tolerance_upper: float = 0.15
    slow: bool = False

    @classmethod
    def fast(cls) -> "CalibrationConfig":
        """CI-fast: small trials, wide tolerances."""
        return cls(n_trials=50, n_obs=80, n_hyp=10, slow=False)

    @classmethod
    def slow_full(cls, n_trials: int = 500, n_obs: int = 200) -> "CalibrationConfig":
        """Slow: larger trials for deeper validation."""
        return cls(n_trials=n_trials, n_obs=n_obs, slow=True)

    @property
    def calibration_harness_schema_version(self) -> int:
        """Schema version for persisted calibration results (artifact contract)."""
        return CALIBRATION_HARNESS_SCHEMA_VERSION
