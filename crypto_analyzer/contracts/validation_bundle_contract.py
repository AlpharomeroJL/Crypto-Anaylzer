"""
Validation bundle schema and level-based validation.
exploratory: ok True, return warnings only.
candidate/accepted: require provenance keys and validation_bundle_schema_version; return ok, blocking reasons, warnings.
"""

from __future__ import annotations

from typing import Tuple

from .schema_versions import VALIDATION_BUNDLE_SCHEMA_VERSION

_REQUIRED_PROVENANCE_KEYS = (
    "dataset_id_v2",
    "dataset_hash_algo",
    "dataset_hash_mode",
    "run_key",
    "engine_version",
    "config_version",
)


def validate_bundle_for_level(
    bundle_dict: dict,
    level: str,
) -> Tuple[bool, list[str], list[str]]:
    """
    Validate bundle (meta dict or bundle.to_dict()) for promotion level.
    Returns (ok, reasons, warnings).
    exploratory: ok True; reasons may list missing keys as warnings.
    candidate/accepted: ok False if required provenance keys missing; reasons are blocking.
    """
    reasons: list[str] = []
    warnings: list[str] = []
    meta = bundle_dict.get("meta", bundle_dict) if isinstance(bundle_dict, dict) else {}

    if level == "exploratory":
        for key in _REQUIRED_PROVENANCE_KEYS:
            val = meta.get(key)
            if not (val is not None and str(val).strip()):
                warnings.append(f"exploratory: missing or empty {key!r} (required for candidate/accepted)")
        if meta.get("dataset_hash_mode") != "STRICT":
            warnings.append("exploratory: dataset_hash_mode is not STRICT (required for promotion)")
        return (True, [], warnings)

    if level not in ("candidate", "accepted"):
        return (True, [], [])

    # Schema version required for candidate/accepted (prevents silent drift)
    vb_ver = meta.get("validation_bundle_schema_version")
    if vb_ver != VALIDATION_BUNDLE_SCHEMA_VERSION:
        reasons.append(f"validation_bundle_schema_version must be {VALIDATION_BUNDLE_SCHEMA_VERSION} (got {vb_ver!r})")

    for key in _REQUIRED_PROVENANCE_KEYS:
        val = meta.get(key)
        if not (val is not None and str(val).strip()):
            reasons.append(f"missing or empty {key!r}")
    if meta.get("dataset_hash_algo") != "sqlite_logical_v2":
        reasons.append("dataset_hash_algo must be sqlite_logical_v2")
    if meta.get("dataset_hash_mode") != "STRICT":
        reasons.append("dataset_hash_mode must be STRICT for promotion")
    ok = len(reasons) == 0
    return (ok, reasons, warnings)
