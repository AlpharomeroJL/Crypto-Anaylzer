"""
Check dataset: print dataset_id_v2 and fingerprint summary.
Replacement for tools/check_dataset.py; uses dataset_v2.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from crypto_analyzer.dataset_v2 import DATASET_HASH_SCOPE_V2, get_dataset_id_v2


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    ap = argparse.ArgumentParser(
        prog="crypto-analyzer check-dataset", description="Print dataset_id_v2 and fingerprint."
    )
    ap.add_argument("--db", default=None, help="DB path (default: from config or CRYPTO_DB_PATH)")
    args, _ = ap.parse_known_args(argv)
    if args.db:
        db = args.db
        root = Path(__file__).resolve().parents[2]
        if not os.path.isabs(db):
            db = str(root / db)
    else:
        try:
            from crypto_analyzer.config import db_path

            p = db_path() if callable(db_path) else db_path
            db = str(p() if callable(p) else p)
        except Exception:
            db = "dex_data.sqlite"
        root = Path(__file__).resolve().parents[2]
        if not os.path.isabs(db):
            db = str(root / db)
    if not os.path.isfile(db):
        print(f"DB not found: {db}", file=sys.stderr)
        return 1
    try:
        dataset_id, meta = get_dataset_id_v2(db, mode="FAST_DEV")
    except ValueError as e:
        print(f"Dataset hash error: {e}", file=sys.stderr)
        return 1
    print(f"dataset_id_v2: {dataset_id}")
    print(f"db_path:       {os.path.basename(db)}")
    print(f"mode:          {meta.get('dataset_hash_mode', 'FAST_DEV')}")
    print(f"scope:         {meta.get('dataset_hash_scope', DATASET_HASH_SCOPE_V2)}")
    if meta.get("warnings"):
        print("warnings:      ", meta["warnings"])
    return 0
