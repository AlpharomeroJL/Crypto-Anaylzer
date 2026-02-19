#!/usr/bin/env python3
"""
Milestone 5 sanity check: imports, spec version, mock manifest write/read.
Run after pulling to verify M5 modules and governance path.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    # 1) Import all new modules
    try:
        import crypto_analyzer.governance as governance
        import crypto_analyzer.spec as spec
    except Exception as e:
        print(f"FAIL: import M5 modules: {e}")
        return 1

    # 2) Print RESEARCH_SPEC_VERSION
    print(f"RESEARCH_SPEC_VERSION: {spec.RESEARCH_SPEC_VERSION}")

    # 3) Tiny mock manifest write/read in temp dir
    with tempfile.TemporaryDirectory() as tmp:
        manifest = governance.make_run_manifest(
            name="sanity_m5",
            args={"test": True},
            data_window={"n_assets": 2, "n_bars": 100},
            outputs={},
            metrics={"dummy": 0.0},
            notes="sanity check",
        )
        path = governance.save_manifest(tmp, manifest)
        if not os.path.isfile(path):
            print("FAIL: manifest file not written")
            return 1
        df = governance.load_manifests(tmp)
        if df.empty or len(df) != 1:
            print("FAIL: load_manifests did not return one row")
            return 1

    # 4) Optionally run a small research_report_v2 path (if DB missing, skip or import-only)
    try:
        from crypto_analyzer.research_universe import get_research_assets

        db = os.environ.get("CRYPTO_DB_PATH", "dex_data.sqlite")
        if not os.path.isabs(db):
            db = str(REPO_ROOT / db)
        if os.path.isfile(db):
            get_research_assets(db, "1h", include_spot=True)
    except Exception as e:
        print(f"Note: get_research_assets skip ({e})")

    # 5) Do NOT run pytest programmatically; print command
    print("Run tests: python -m pytest tests/ -q")

    print("OK: Milestone 5 sanity check complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
