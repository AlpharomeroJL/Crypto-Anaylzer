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
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .artifacts import ensure_dir, write_json
from .spec import spec_summary


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


def now_utc_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
    write_json(manifest, path)
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
