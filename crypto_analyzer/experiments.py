"""
Lightweight local experiment logging. Research-only.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd


def _git_hash() -> Optional[str]:
    try:
        import subprocess
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))) or ".",
        )
        return (r.stdout or "").strip() or None
    except Exception:
        return None


def log_experiment(
    run_name: str,
    config_dict: Dict[str, Any],
    metrics_dict: Dict[str, Any],
    artifacts_paths: Optional[List[str]] = None,
    out_dir: str = "reports/experiments",
) -> str:
    """
    Write experiment JSON (timestamp, git hash, config, metrics) and append a row to experiments.csv.
    Returns path to the written JSON file.
    """
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    git = _git_hash()
    payload = {
        "run_name": run_name,
        "timestamp": ts,
        "git_commit": git,
        "config": config_dict,
        "metrics": metrics_dict,
        "artifacts": list(artifacts_paths or []),
    }
    # Safe JSON (non-serializable -> str)
    def _enc(o: Any) -> Any:
        if isinstance(o, dict):
            return {str(k): _enc(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_enc(x) for x in o]
        if isinstance(o, (pd.Timestamp, datetime)):
            return o.isoformat()
        if hasattr(o, "item") and callable(o.item):
            try:
                return o.item()
            except Exception:
                return str(o)
        if isinstance(o, (float, int, str, bool, type(None))):
            return o
        return str(o)

    payload_enc = _enc(payload)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in run_name)[:80]
    fname = f"{safe_name}_{ts[:19].replace(':', '-')}.json"
    path = os.path.join(out_dir, fname)
    with open(path, "w") as f:
        json.dump(payload_enc, f, indent=2)
    # Append to experiments.csv
    csv_path = os.path.join(out_dir, "experiments.csv")
    row = {
        "run_name": run_name,
        "timestamp": ts,
        "git_commit": git or "",
        **{f"metric_{k}": v for k, v in (metrics_dict or {}).items()},
    }
    df_row = pd.DataFrame([row])
    if os.path.isfile(csv_path):
        df_row.to_csv(csv_path, mode="a", header=False, index=False)
    else:
        df_row.to_csv(csv_path, mode="w", header=True, index=False)
    return path


def load_experiments(out_dir: str = "reports/experiments") -> pd.DataFrame:
    """Load experiments table from experiments.csv."""
    csv_path = os.path.join(out_dir, "experiments.csv")
    if not os.path.isfile(csv_path):
        return pd.DataFrame()
    return pd.read_csv(csv_path)
