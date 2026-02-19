"""
Stable family_id for Reality Check / Romano–Wolf: canonical hash of config + signals + horizons + estimator + params + regime.
No timestamps; sorted keys and lists for determinism. Phase 3 Slice 4.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict


def _canonicalize(value: Any) -> Any:
    """Recursively canonicalize for hashing: sort dict keys, sort lists, no timestamps."""
    if isinstance(value, dict):
        return {str(k): _canonicalize(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return sorted(_canonicalize(x) for x in value)
    if isinstance(value, (int, float, str, bool, type(None))):
        return value
    return str(value)


def compute_family_id(payload: Dict[str, Any]) -> str:
    """
    Stable family_id from payload (config_hash, signals, horizons, estimator, params, regime_run_id, etc.).
    payload keys and list elements are sorted; no timestamps. Returns short hash prefix (e.g. rcfam_ + 16 hex).
    """
    canonical = _canonicalize(payload)
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    h = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return f"rcfam_{h[:16]}"
