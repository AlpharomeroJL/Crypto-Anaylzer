"""Re-export central RNG from crypto_analyzer.rng (avoids circular import with statistics)."""

from __future__ import annotations

from crypto_analyzer.rng import (
    SALT_BLOCK_FIXED_BOOTSTRAP,
    SALT_CALIBRATION,
    SALT_CSCV_SPLITS,
    SALT_NULL_DGP,
    SALT_RC_NULL,
    SALT_RW_STEPDOWN,
    SALT_STATIONARY_BOOTSTRAP,
    SEED_ROOT_VERSION,
    rng_for,
    rng_from_seed,
    seed_root,
)

__all__ = [
    "SEED_ROOT_VERSION",
    "SALT_BLOCK_FIXED_BOOTSTRAP",
    "SALT_CALIBRATION",
    "SALT_CSCV_SPLITS",
    "SALT_NULL_DGP",
    "SALT_RC_NULL",
    "SALT_RW_STEPDOWN",
    "SALT_STATIONARY_BOOTSTRAP",
    "rng_for",
    "rng_from_seed",
    "seed_root",
]
