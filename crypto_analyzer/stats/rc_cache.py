"""
RC null simulation cache: keyed by family_id + rc config + dataset_id + git_commit.
Phase 3 Slice 5. No-cache: CRYPTO_ANALYZER_NO_CACHE=1 or caller passes use_cache=False.
Uses cache_flags.is_cache_disabled as single source of truth (PR3).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from crypto_analyzer.artifacts import compute_file_sha256, ensure_dir
from crypto_analyzer.stats.cache_flags import is_cache_disabled as _is_cache_disabled

# Bump when RC algorithm changes so cached nulls are invalidated.
RC_ALGO_VERSION = "v1"


def get_rc_cache_key(
    family_id: str,
    dataset_id: str,
    git_commit: str,
    rc_metric: str,
    rc_horizon: Optional[int],
    rc_n_sim: int,
    rc_seed: int,
    rc_method: str,
    rc_avg_block_length: int,
) -> str:
    """Stable cache key for RC null distribution. No timestamps. Includes algo version for invalidation on RC changes."""
    payload = (
        f"{RC_ALGO_VERSION}|{family_id}|{dataset_id}|{git_commit}|{rc_metric}|{rc_horizon}|"
        f"{rc_n_sim}|{rc_seed}|{rc_method}|{rc_avg_block_length}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _manifest_path(cache_dir: Path) -> Path:
    return cache_dir / "manifest.json"


def _null_max_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"null_max_{key}.npy"


def load_manifest(cache_dir: Path) -> Dict[str, Any]:
    """Read manifest: key -> {path, sha256}. Empty dict if missing."""
    p = _manifest_path(cache_dir)
    if not p.is_file():
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_manifest(cache_dir: Path, manifest: Dict[str, Any]) -> None:
    """Write manifest with sorted keys. Atomic: write to .tmp then rename."""
    ensure_dir(cache_dir)
    p = _manifest_path(cache_dir)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    tmp.replace(p)


def load_cached_null_max(cache_dir: str | Path, key: str) -> Optional[np.ndarray]:
    """
    Load cached null_max distribution (1d array). Returns None if missing or invalid.
    """
    cache_dir = Path(cache_dir)
    manifest = load_manifest(cache_dir)
    if key not in manifest:
        return None
    path = cache_dir / manifest[key].get("path", f"null_max_{key}.npy")
    if not path.is_file():
        return None
    expected_sha = manifest[key].get("sha256")
    if expected_sha and compute_file_sha256(path) != expected_sha:
        return None
    try:
        arr = np.load(path)
        return np.asarray(arr, dtype=float).ravel()
    except Exception:
        return None


def save_cached_null_max(
    cache_dir: str | Path,
    key: str,
    null_max: np.ndarray,
) -> None:
    """Save null_max array and update manifest (path + sha256)."""
    cache_dir = Path(cache_dir)
    ensure_dir(cache_dir)
    path = _null_max_path(cache_dir, key)
    np.save(path, np.asarray(null_max, dtype=float))
    sha = compute_file_sha256(path)
    manifest = load_manifest(cache_dir)
    rel_path = path.name
    manifest[key] = {"path": rel_path, "sha256": sha}
    save_manifest(cache_dir, manifest)


def is_cache_disabled(no_cache_flag: bool = False) -> bool:
    """True if cache should be disabled. Delegates to cache_flags.is_cache_disabled (single source of truth)."""
    return _is_cache_disabled(no_cache_flag=no_cache_flag)
