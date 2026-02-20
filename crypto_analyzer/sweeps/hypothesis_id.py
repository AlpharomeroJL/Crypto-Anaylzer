"""
Stable hypothesis_id for sweep registry: canonical hash of signal_name, horizon, estimator, params, regime_run_id.
No timestamps; sorted keys and lists for determinism. Phase 3 sweep registry hardening.
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


def compute_hypothesis_id(payload: Dict[str, Any]) -> str:
    """
    Stable hypothesis_id from payload (signal_name, horizon, estimator, params, regime_run_id).
    payload keys and list elements are sorted; no timestamps. Returns short hash (e.g. hyp_ + 16 hex).
    """
    canonical = _canonicalize(payload)
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    h = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return f"hyp_{h[:16]}"
