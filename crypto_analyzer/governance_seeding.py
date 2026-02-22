"""
Deterministic seeding from run_key for reportv2 and stats procedures.
Delegates to crypto_analyzer.stats.rng (single auditable RNG root).
No global RNG mutation; all randomness via np.random.Generator from derived seeds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from crypto_analyzer.rng import rng_for as _rng_for_central
from crypto_analyzer.rng import seed_root as _seed_root_central

if TYPE_CHECKING:
    pass


def seed_for(component: str, run_key: str, salt: str = "") -> int:
    """
    Derive a stable 64-bit unsigned seed from component, run_key, and salt.
    Same (component, run_key, salt) always yields the same seed.
    Implemented via stats.rng.seed_root for a single auditable RNG root.
    """
    return _seed_root_central(run_key, salt=f"{component}|{salt}")


def rng_for(component: str, run_key: str, salt: str = "") -> np.random.Generator:
    """
    Return a numpy Generator seeded from seed_for(component, run_key, salt).
    Implemented via stats.rng.rng_for for a single auditable RNG root.
    """
    return _rng_for_central(run_key, salt=f"{component}|{salt}")
