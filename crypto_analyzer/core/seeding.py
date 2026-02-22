"""
Canonical RNG seeding: single deterministic seed root from run_key + component salt.
All stochastic procedures must derive randomness via rng_for(run_key, salt).
Never use Python's built-in hash() (not stable across processes).

Contract: seed_root versioning
- SEED_ROOT_VERSION is the current version of the hashing scheme (salts, encoding, algorithm).
- If you change hashing scheme, salt set, or encoding, bump SEED_ROOT_VERSION.
- Store seed_version in artifacts alongside seed_root so "same run_key, different engine →
  different nulls" is explainable and seed_version can be used for promotion eligibility later.
"""

from __future__ import annotations

import hashlib
from typing import Optional, Union

import numpy as np

# Version of seed_root derivation; bump when hashing scheme / salt set / encoding changes
SEED_ROOT_VERSION = 1

# Component-scoped salt names for auditability (single canonical module; reference these, never string literals)
SALT_STATIONARY_BOOTSTRAP = "stationary_bootstrap"
SALT_BLOCK_FIXED_BOOTSTRAP = "block_fixed_bootstrap"
SALT_RC_NULL = "rc_null"
SALT_RW_STEPDOWN = "rw_stepdown"
SALT_CSCV_SPLITS = "cscv_splits"
SALT_CALIBRATION = "calibration"
SALT_NULL_DGP = "null_dgp"
SALT_FOLD_SPLITS = "fold_splits"
SALT_FOLD_ATTESTATION = "fold_attestation"


def seed_root(
    run_key: str,
    *,
    salt: str,
    fold_id: Optional[Union[str, int]] = None,
    version: int = SEED_ROOT_VERSION,
) -> int:
    """
    Derive a stable 64-bit unsigned seed from run_key and component salt.
    Same (run_key, salt, fold_id, version) yields the same seed across process runs.
    Uses SHA-256 (never Python hash()). Use fold_id for substreams (e.g. family_id, hypothesis_id).
    fold_id is normalized to str and prefixed with "fold:" to avoid collisions with raw hypothesis IDs.
    """
    if fold_id is not None:
        fold_normalized = f"fold:{str(fold_id)}"
        salt_effective = f"{salt}|{fold_normalized}"
    else:
        salt_effective = salt
    payload = f"{run_key}|{salt_effective}|{version}".encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    seed = int.from_bytes(digest[:8], byteorder="big")
    return seed % (2**63)


def rng_for(
    run_key: str,
    salt: str,
    fold_id: Optional[Union[str, int]] = None,
    version: int = SEED_ROOT_VERSION,
) -> np.random.Generator:
    """
    Return a numpy Generator seeded from seed_root(run_key, salt=salt, fold_id=fold_id, version=version).
    Use for all stochastic procedures in Phase 2A.
    """
    seed = seed_root(run_key, salt=salt, fold_id=fold_id, version=version)
    return np.random.default_rng(seed)


def rng_from_seed(seed: Optional[int]) -> np.random.Generator:
    """
    Build a Generator from an explicit seed (e.g. when run_key is not available).
    Callers should prefer rng_for(run_key, salt) when run_key exists.
    If seed is None, returns a non-deterministic generator; do not use in paths
    that produce candidate/accepted artifacts.
    """
    if seed is not None:
        return np.random.default_rng(seed)
    return np.random.default_rng()


__all__ = [
    "SEED_ROOT_VERSION",
    "seed_root",
    "rng_for",
    "rng_from_seed",
    "SALT_BLOCK_FIXED_BOOTSTRAP",
    "SALT_CALIBRATION",
    "SALT_CSCV_SPLITS",
    "SALT_FOLD_ATTESTATION",
    "SALT_FOLD_SPLITS",
    "SALT_NULL_DGP",
    "SALT_RC_NULL",
    "SALT_RW_STEPDOWN",
    "SALT_STATIONARY_BOOTSTRAP",
]
