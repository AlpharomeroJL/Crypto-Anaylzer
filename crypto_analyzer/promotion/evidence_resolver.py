"""
Evidence resolution: paths -> loaded objects (bundle, regime, RC, execution evidence).
Isolates all path loading and parsing; no gating or persistence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import pandas as pd

from crypto_analyzer.validation_bundle import ValidationBundle

from .execution_evidence import ExecutionEvidence


def _load_bundle(path: Union[str, Path]) -> Optional[ValidationBundle]:
    """Load ValidationBundle from JSON path. Returns None if file missing or invalid."""
    path = Path(path)
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return ValidationBundle(
            run_id=d.get("run_id", ""),
            dataset_id=d.get("dataset_id", ""),
            signal_name=d.get("signal_name", ""),
            freq=d.get("freq", ""),
            horizons=d.get("horizons", []),
            ic_summary_by_horizon={int(k): v for k, v in (d.get("ic_summary_by_horizon") or {}).items()},
            ic_decay_table=d.get("ic_decay_table", []),
            meta=d.get("meta", {}),
            ic_series_path_by_horizon={int(k): v for k, v in (d.get("ic_series_path_by_horizon") or {}).items()},
            ic_decay_path=d.get("ic_decay_path"),
            turnover_path=d.get("turnover_path"),
            gross_returns_path=d.get("gross_returns_path"),
            net_returns_path=d.get("net_returns_path"),
            ic_summary_by_regime_path=d.get("ic_summary_by_regime_path"),
            ic_decay_by_regime_path=d.get("ic_decay_by_regime_path"),
            regime_coverage_path=d.get("regime_coverage_path"),
        )
    except Exception:
        return None


def _load_regime_summary(path: Union[str, Path]) -> Optional[pd.DataFrame]:
    """Load regime summary CSV. Returns None if missing."""
    path = Path(path)
    if not path.is_file():
        return None
    try:
        return pd.read_csv(path)
    except Exception:
        return None


def _load_rc_summary(path: Union[str, Path]) -> Optional[Dict[str, Any]]:
    """Load RC summary JSON. Returns None if missing."""
    path = Path(path)
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_execution_evidence(path: Union[str, Path]) -> Optional[ExecutionEvidence]:
    """Load ExecutionEvidence from JSON file. Returns None if missing or invalid."""
    path = Path(path)
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return ExecutionEvidence.from_dict(d)
    except Exception:
        return None


def resolve_evidence(
    evidence_json: Dict[str, Any],
    evidence_base_path: Union[str, Path],
    bundle_or_path: Union[ValidationBundle, str, Path],
) -> Tuple[
    Optional[ValidationBundle],
    Optional[pd.DataFrame],
    Optional[Dict[str, Any]],
    Optional[ExecutionEvidence],
]:
    """
    Resolve evidence from paths in evidence_json and load bundle if path given.

    Returns (bundle, regime_summary_df, rc_summary, execution_evidence).
    Any of these may be None if not provided or load failed.
    """
    base = Path(evidence_base_path) if evidence_base_path else Path(".")

    bundle: Optional[ValidationBundle] = None
    if isinstance(bundle_or_path, ValidationBundle):
        bundle = bundle_or_path
    else:
        bundle = _load_bundle(bundle_or_path)

    regime_summary_df: Optional[pd.DataFrame] = None
    if evidence_json.get("ic_summary_by_regime_path"):
        p = (
            base / evidence_json["ic_summary_by_regime_path"]
            if not Path(evidence_json["ic_summary_by_regime_path"]).is_absolute()
            else Path(evidence_json["ic_summary_by_regime_path"])
        )
        regime_summary_df = _load_regime_summary(p)

    rc_summary: Optional[Dict[str, Any]] = None
    if evidence_json.get("rc_summary_path"):
        p = (
            base / evidence_json["rc_summary_path"]
            if not Path(evidence_json["rc_summary_path"]).is_absolute()
            else Path(evidence_json["rc_summary_path"])
        )
        rc_summary = _load_rc_summary(p)

    execution_evidence: Optional[ExecutionEvidence] = None
    exec_path = evidence_json.get("execution_evidence_path")
    if exec_path:
        p = base / exec_path if not Path(exec_path).is_absolute() else Path(exec_path)
        execution_evidence = _load_execution_evidence(p)

    return bundle, regime_summary_df, rc_summary, execution_evidence
