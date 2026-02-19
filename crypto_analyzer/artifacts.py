"""
Artifact I/O and hashing for reports. Research-only.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


def ensure_dir(path: str | Path) -> None:
    """Create directory and parents if they do not exist."""
    Path(path).mkdir(parents=True, exist_ok=True)


def write_df_csv(df: pd.DataFrame, path: str | Path) -> None:
    """Write DataFrame to CSV with UTF-8 encoding."""
    path = Path(path)
    ensure_dir(path.parent)
    df.to_csv(path, index=False, encoding="utf-8")


def write_json(obj: Any, path: str | Path) -> None:
    """Write JSON-serializable object to file (UTF-8)."""
    path = Path(path)
    ensure_dir(path.parent)

    def _enc(o: Any) -> Any:
        if isinstance(o, dict):
            return {str(k): _enc(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_enc(x) for x in o]
        if hasattr(o, "item") and callable(o.item):
            try:
                return o.item()
            except Exception:
                return str(o)
        if isinstance(o, (float, int, str, bool, type(None))):
            return o
        if hasattr(o, "isoformat"):
            return o.isoformat()
        return str(o)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(_enc(obj), f, indent=2)


def write_text(text: str, path: str | Path) -> None:
    """Write text to file (UTF-8)."""
    path = Path(path)
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def compute_file_sha256(path: str | Path) -> str:
    """Return SHA256 hex digest of file. Returns empty string if file missing or unreadable."""
    path = Path(path)
    if not path.is_file():
        return ""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def snapshot_outputs(paths: List[str]) -> Dict[str, str]:
    """Return dict mapping each path to its SHA256 hex digest (empty if missing)."""
    return {p: compute_file_sha256(p) for p in paths}


def df_to_download_bytes(df: pd.DataFrame) -> bytes:
    """Return UTF-8-encoded CSV bytes for Streamlit download_button. Always use this for downloads."""
    return df.to_csv(index=False).encode("utf-8")


def timestamped_filename(prefix: str, ext: str, sep: str = "_") -> str:
    """Return a filename like prefix_YYYYMMDD_HHMM.ext using UTC."""
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    return f"{prefix}{sep}{ts}.{ext}"
