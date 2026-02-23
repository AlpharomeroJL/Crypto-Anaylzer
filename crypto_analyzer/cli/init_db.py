"""
Initialize a local SQLite DB: create file, run core and optional Phase 3 migrations.
Use: crypto-analyzer init [--db PATH] [--phase3]
Default DB path: data/crypto_analyzer.sqlite (repo-local).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    ap = argparse.ArgumentParser(
        prog="crypto-analyzer init",
        description="Create local SQLite DB and run migrations (core + optional Phase 3).",
    )
    ap.add_argument(
        "--db",
        default="data/crypto_analyzer.sqlite",
        help="DB path (default: data/crypto_analyzer.sqlite)",
    )
    ap.add_argument(
        "--phase3",
        action="store_true",
        help="Run Phase 3 migrations (governance, promotion, lineage).",
    )
    args = ap.parse_args(argv)
    db_path = Path(args.db)
    if not db_path.is_absolute():
        # Repo root: parent of crypto_analyzer package
        root = Path(__file__).resolve().parents[2]
        db_path = root / db_path
    db_path = db_path.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    path_str = str(db_path)
    try:
        with sqlite3.connect(path_str) as conn:
            from crypto_analyzer.db.migrations import run_migrations

            run_migrations(conn, path_str)
            if args.phase3:
                from crypto_analyzer.db.migrations_phase3 import run_migrations_phase3

                run_migrations_phase3(conn, path_str)
        print(f"Initialized DB: {path_str}")
        return 0
    except Exception as e:
        print(f"init failed: {e}", file=sys.stderr)
        return 1
