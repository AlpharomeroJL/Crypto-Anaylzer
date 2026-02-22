"""
Fold-causality attestation artifact: schema version, run identity, split summary, transforms, enforcement checks.
Persisted alongside bundle; required for candidate/accepted when walk-forward used.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .folds import SplitPlan

FOLD_CAUSALITY_ATTESTATION_SCHEMA_VERSION = 1


def build_fold_causality_attestation(
    run_key: str,
    dataset_id_v2: str,
    split_plan: SplitPlan,
    transforms_used: List[Dict[str, Any]],
    checks: Dict[str, bool],
    *,
    engine_version: str = "",
    config_version: str = "",
    seed_root: Optional[int] = None,
    seed_salt: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build attestation dict for persistence. checks must include:
    train_only_fit_enforced, purge_applied, embargo_applied, no_future_rows_in_fit.
    """
    summary = {
        "n_folds": len(split_plan.folds),
        "split_plan_schema_version": split_plan.split_plan_schema_version,
        "purge_embargo_asof": [
            {
                "fold_id": f.fold_id,
                "purge_gap_bars": f.purge_gap_bars,
                "embargo_bars": f.embargo_bars,
                "asof_lag_bars": f.asof_lag_bars,
            }
            for f in split_plan.folds
        ],
    }
    if split_plan.folds:
        f0 = split_plan.folds[0]
        summary["train_end_sample"] = str(f0.train_end_ts)
        summary["test_start_sample"] = str(f0.test_start_ts)
    out = {
        "fold_causality_attestation_schema_version": FOLD_CAUSALITY_ATTESTATION_SCHEMA_VERSION,
        "run_key": run_key,
        "dataset_id_v2": dataset_id_v2,
        "engine_version": engine_version,
        "config_version": config_version,
        "split_plan_summary": summary,
        "transforms": list(transforms_used),
        "enforcement_checks": dict(checks),
    }
    if seed_root is not None:
        out["seed_root"] = seed_root
    if seed_salt is not None:
        out["seed_salt"] = seed_salt
    return out


def validate_attestation(att: Dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate attestation for gatekeeper. Returns (ok, list of blocker messages).
    """
    blockers: list[str] = []
    if att.get("fold_causality_attestation_schema_version") != FOLD_CAUSALITY_ATTESTATION_SCHEMA_VERSION:
        blockers.append(
            f"fold_causality_attestation_schema_version must be {FOLD_CAUSALITY_ATTESTATION_SCHEMA_VERSION}"
        )
    required_checks = [
        "train_only_fit_enforced",
        "purge_applied",
        "embargo_applied",
        "no_future_rows_in_fit",
    ]
    ec = att.get("enforcement_checks") or {}
    for k in required_checks:
        if ec.get(k) is not True:
            blockers.append(f"enforcement_checks.{k} must be true")
    return (len(blockers) == 0, blockers)
