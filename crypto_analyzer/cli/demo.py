#!/usr/bin/env python3
"""
One-command demo: preflight, collect minimal data, materialize, generate report.
Research-only; no execution layer.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

# Repo root (crypto_analyzer/cli/demo.py -> parents[2] = repo)
_root = Path(__file__).resolve().parents[2]
_py = sys.executable


def _run(args: list[str], label: str, check: bool = True) -> int:
    """Run a subprocess with the venv Python, printing the label."""
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}\n")
    result = subprocess.run([_py] + args, cwd=str(_root))
    if check and result.returncode != 0:
        print(f"\nFAILED: {label} (exit {result.returncode})")
        sys.exit(result.returncode)
    return result.returncode


def main(argv: Optional[List[str]] = None) -> int:
    # Preflight: must be in repo root
    if not os.path.isfile(os.path.join(str(_root), "config.yaml")):
        print("config.yaml not found. Run from repo root.")
        return 2

    # Step 1: Doctor
    _run(["-m", "crypto_analyzer.doctor"], "Step 1: Doctor (preflight checks)")

    # Step 2: Check if DB exists; if not, poll briefly
    from crypto_analyzer.config import db_path as _db_path_fn

    _dbp = _db_path_fn() if callable(_db_path_fn) else _db_path_fn
    db = str(_dbp() if callable(_dbp) else _dbp)
    if not os.path.isabs(db):
        db = str(_root / db)

    if not os.path.isfile(db):
        print("\nNo database found. Running a short data collection (30s)...")
        _run(
            [
                "-m",
                "crypto_analyzer",
                "universe-poll",
                "--universe-chain",
                "solana",
                "--interval",
                "5",
                "--run-seconds",
                "30",
            ],
            "Step 2a: Collect minimal data (30s poll)",
        )
    else:
        print(f"\nDatabase exists: {os.path.basename(db)}")

    # Step 3: Materialize 1h bars
    _run(
        ["-m", "crypto_analyzer", "materialize", "--freq", "1h"],
        "Step 3: Materialize 1h bars",
    )

    # Step 4: Generate report + experiment
    _run(
        ["-m", "crypto_analyzer", "reportv2", "--freq", "1h", "--out-dir", "reports"],
        "Step 4: Generate research report (reportv2)",
    )

    # Step 5: Print dataset_id
    _run(
        ["-m", "crypto_analyzer", "check-dataset"],
        "Step 5: Dataset fingerprint",
    )

    # Step 6: Next steps
    print(f"\n{'=' * 60}")
    print("  Demo complete!")
    print(f"{'=' * 60}\n")
    print("Next steps (copy-paste into your terminal):\n")
    print("  Start API:")
    print("    .\\scripts\\run.ps1 api --host 127.0.0.1 --port 8001\n")
    print("  Health check:")
    print("    curl.exe http://127.0.0.1:8001/health\n")
    print("  Recent experiments:")
    print("    curl.exe http://127.0.0.1:8001/experiments/recent\n")
    print("  Interactive dashboard:")
    print("    .\\scripts\\run.ps1 streamlit\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
