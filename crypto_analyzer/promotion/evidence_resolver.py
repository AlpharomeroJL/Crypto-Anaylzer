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


def _resolve_relative_file_path(rel: str, directory_base: Union[str, Path, None]) -> Path:
    """
    Resolve a relative path to an on-disk file for promotion evidence loading.

    Tries, in order: (directory_base / rel), (cwd / rel), (rel as given). This matches
    create/evaluate usage where stored paths may be repo-root-relative (e.g. reports/csv/x.json)
    while evaluate passes directory_base = parent(bundle_path) (e.g. reports/csv), which must
    not be prepended twice.
    """
    rel_stripped = (rel or "").strip()
    if not rel_stripped:
        return Path(rel_stripped)
    p = Path(rel_stripped)
    if p.is_absolute():
        return p
    db = Path(directory_base) if directory_base is not None else Path(".")
    candidates = [db / p, Path.cwd() / p, p]
    seen: set[str] = set()
    for cand in candidates:
        try:
            key = str(cand.resolve())
        except OSError:
            key = str(cand)
        if key in seen:
            continue
        seen.add(key)
        try:
            if cand.is_file():
                return cand
        except OSError:
            continue
    return db / p


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
        bstr = str(bundle_or_path).strip() if bundle_or_path is not None else ""
        if not bstr:
            bundle = None
        else:
            bundle = _load_bundle(_resolve_relative_file_path(bstr, base))

    regime_summary_df: Optional[pd.DataFrame] = None
    if evidence_json.get("ic_summary_by_regime_path"):
        rp = evidence_json["ic_summary_by_regime_path"]
        p = Path(rp) if Path(rp).is_absolute() else _resolve_relative_file_path(str(rp), base)
        regime_summary_df = _load_regime_summary(p)

    rc_summary: Optional[Dict[str, Any]] = None
    if evidence_json.get("rc_summary_path"):
        rp = evidence_json["rc_summary_path"]
        p = Path(rp) if Path(rp).is_absolute() else _resolve_relative_file_path(str(rp), base)
        rc_summary = _load_rc_summary(p)

    execution_evidence: Optional[ExecutionEvidence] = None
    exec_path = evidence_json.get("execution_evidence_path")
    if exec_path:
        p = Path(exec_path) if Path(exec_path).is_absolute() else _resolve_relative_file_path(str(exec_path), base)
        execution_evidence = _load_execution_evidence(p)

    return bundle, regime_summary_df, rc_summary, execution_evidence
