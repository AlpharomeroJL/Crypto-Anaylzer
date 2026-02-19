#!/usr/bin/env python3
"""Print dataset_id and fingerprint summary. No external deps beyond existing."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.dataset import (
    compute_dataset_fingerprint,
    dataset_id_from_fingerprint,
    fingerprint_to_json,
)


def main() -> int:
    # Resolve DB path
    try:
        from crypto_analyzer.config import db_path

        p = db_path() if callable(db_path) else db_path
        db = str(p() if callable(p) else p)
    except Exception:
        db = "dex_data.sqlite"
    if not os.path.isabs(db):
        db = str(_root / db)

    if not os.path.isfile(db):
        print(f"DB not found: {db}")
        return 1

    fp = compute_dataset_fingerprint(db)
    did = dataset_id_from_fingerprint(fp)

    print(f"dataset_id: {did}")
    print(f"db_path:    {os.path.basename(db)}")
    print(f"created:    {fp.created_ts_utc}")
    print()
    print("Tables:")
    for t in fp.tables:
        ts_range = f"  {t.min_ts} .. {t.max_ts}" if t.min_ts else ""
        print(f"  {t.table:<30s} rows={t.row_count:<10d}{ts_range}")
    if fp.integrity:
        print()
        print("Integrity:")
        for key, info in fp.integrity.items():
            print(f"  {key}: bad={info['bad']}/{info['total']} rate={info['rate']:.4%}")
    print()
    print("Fingerprint JSON:")
    print(fingerprint_to_json(fp))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
