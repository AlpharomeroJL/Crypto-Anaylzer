"""
Reproducible run registry: manifests with git, env fingerprint, data window, outputs, metrics.
Research-only; no execution.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from .artifacts import ensure_dir, write_json_sorted
from .spec import spec_summary
from .timeutils import now_utc_iso

# Keys to exclude from run_key (semantic identity must not depend on these)
_RUN_KEY_EXCLUDE_KEYS = frozenset({"ts_utc", "created_utc", "timestamp", "out_dir", "output_dir", "path", "paths"})


@dataclass
class RunIdentity:
    """Phase 1 run identity: run_key (semantic) + run_instance_id (execution-specific)."""

    run_key: str
    run_instance_id: str
    run_identity_schema_version: int = 1
    engine_version: str = ""
    config_version: str = ""
    research_spec_version: str = ""
    pipeline_contract_version: str = ""


def get_git_commit() -> str:
    """Return short git commit hash or 'unknown' if git not available."""
    try:
        root = Path(__file__).resolve().parent.parent
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=str(root),
        )
        out = (r.stdout or "").strip()
        return out if out else "unknown"
    except Exception:
        return "unknown"


def get_env_fingerprint() -> dict:
    """Return dict with python version, platform, and key package versions."""
    out = {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
    }
    for pkg in ("numpy", "pandas", "streamlit"):
        try:
            mod = __import__(pkg)
            out[pkg] = getattr(mod, "__version__", "?")
        except Exception:
            out[pkg] = "not_installed"
    return out


def stable_run_id(payload: dict) -> str:
    """Return a stable hash of the payload (e.g. for reproducibility)."""
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _payload_for_run_key(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Strip keys that must not affect run_key (timestamps, paths)."""
    out: Dict[str, Any] = {}
    for k, v in payload.items():
        if k in _RUN_KEY_EXCLUDE_KEYS:
            continue
        if isinstance(v, dict):
            out[k] = _payload_for_run_key(v)
        elif isinstance(v, list):
            out[k] = [_payload_for_run_key(x) if isinstance(x, dict) else x for x in v]
        else:
            out[k] = v
    return out


def compute_run_key(payload: dict) -> str:
    """
    Deterministic run_key from semantic payload only.
    Must include: dataset_id_v2, semantic config (signals, horizons, toggles, RC/RW config),
    version pins (engine_version, config_version, research_spec_version).
    Must exclude: timestamps (ts_utc, created_utc), file paths.
    """
    cleaned = _payload_for_run_key(payload)
    blob = json.dumps(cleaned, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def build_run_identity(
    semantic_payload: Dict[str, Any],
    run_instance_id: str,
    *,
    engine_version: str = "",
    config_version: str = "",
    research_spec_version: str = "",
    pipeline_contract_version: str = "",
) -> RunIdentity:
    """Build RunIdentity: compute_run_key(semantic_payload) + instance id and version pins."""
    run_key = compute_run_key(semantic_payload)
    return RunIdentity(
        run_key=run_key,
        run_instance_id=run_instance_id,
        run_identity_schema_version=1,
        engine_version=engine_version or get_git_commit(),
        config_version=config_version,
        research_spec_version=research_spec_version,
        pipeline_contract_version=pipeline_contract_version,
    )


def make_run_manifest(
    name: str,
    args: dict,
    data_window: dict,
    outputs: dict,
    metrics: dict,
    notes: str = "",
) -> dict:
    """
    Build manifest dict with run_id, created_utc, git_commit, env_fingerprint,
    args, data_window, outputs, metrics, spec, notes.
    """
    created = now_utc_iso()
    payload = {
        "name": name,
        "args": args,
        "data_window": data_window,
        "created_utc": created,
    }
    run_id = stable_run_id(payload)
    manifest = {
        "run_id": run_id,
        "created_utc": created,
        "name": name,
        "git_commit": get_git_commit(),
        "env_fingerprint": get_env_fingerprint(),
        "spec": spec_summary(),
        "args": args,
        "data_window": data_window,
        "outputs": outputs,
        "metrics": metrics,
        "notes": notes,
    }
    return manifest


def append_run_registry(out_dir: str | Path, run_id: str, manifest_path: str) -> None:
    """Append one JSON line to out_dir/run_registry.jsonl (run_id, manifest path, timestamp)."""
    out_dir = Path(out_dir)
    registry_path = out_dir / "run_registry.jsonl"
    line = (
        json.dumps(
            {
                "run_id": run_id,
                "manifest_path": manifest_path,
                "timestamp": now_utc_iso(),
            }
        )
        + "\n"
    )
    try:
        with open(registry_path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def save_manifest(out_dir: str | Path, manifest: dict) -> str:
    """Write manifest JSON to out_dir/manifests/<run_id>.json. Return path."""
    out_dir = Path(out_dir)
    manifests_dir = out_dir / "manifests"
    ensure_dir(manifests_dir)
    run_id = manifest.get("run_id", "unknown")
    path = manifests_dir / f"{run_id}.json"
    write_json_sorted(manifest, path)
    manifest_path_str = str(path)
    append_run_registry(out_dir, run_id, manifest_path_str)
    return manifest_path_str


def load_manifests(out_dir: str | Path) -> pd.DataFrame:
    """Load all manifest JSONs from out_dir/manifests into a flat DataFrame."""
    out_dir = Path(out_dir)
    manifests_dir = out_dir / "manifests"
    if not manifests_dir.is_dir():
        return pd.DataFrame()

    rows = []
    for path in sorted(manifests_dir.glob("*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                m = json.load(f)
            spec = m.get("spec") or {}
            outputs = m.get("outputs") or {}
            rows.append(
                {
                    "run_id": m.get("run_id"),
                    "created_utc": m.get("created_utc"),
                    "name": m.get("name"),
                    "git_commit": m.get("git_commit"),
                    "spec_version": spec.get("research_spec_version", ""),
                    "outputs": ", ".join(outputs.keys()) if isinstance(outputs, dict) else str(outputs),
                    "path": str(path),
                }
            )
        except Exception:
            continue
    return pd.DataFrame(rows)
