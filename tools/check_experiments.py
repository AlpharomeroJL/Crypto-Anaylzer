#!/usr/bin/env python3
"""
Print a quick summary of the experiment registry (SQLite).
Usage: .\.venv\Scripts\python.exe tools/check_experiments.py [--db reports/experiments.db]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crypto_analyzer.experiments import (
    load_experiments,
    load_distinct_metric_names,
    load_metric_history,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Check experiment registry")
    ap.add_argument("--db", default=os.environ.get("EXPERIMENT_DB_PATH", "reports/experiments.db"))
    args = ap.parse_args()

    dsn = os.environ.get("EXPERIMENT_DB_DSN")
    db = args.db
    if dsn:
        host_part = dsn.split("@")[-1].split("/")[0] if "@" in dsn else dsn[:40]
        print(f"Backend: Postgres (host={host_part})")
    else:
        print(f"Backend: SQLite")
    if not os.path.isfile(db) and not dsn:
        print(f"No experiment DB at {db}. Run reportv2 first.")
        return 0

    print(f"=== Experiment Registry: {db} ===\n")

    exps = load_experiments(db, limit=5)
    if exps.empty:
        print("No experiments recorded.")
    else:
        print(f"Last {len(exps)} experiments:")
        for _, row in exps.iterrows():
            print(f"  {row['run_id']}  {row['ts_utc']}  git={row.get('git_commit', '?')}  spec={row.get('spec_version', '?')}")
        print()

    mnames = load_distinct_metric_names(db)
    if mnames:
        print(f"Available metrics ({len(mnames)}):")
        for m in mnames:
            hist = load_metric_history(db, m, limit=1)
            latest = f"{hist['metric_value'].iloc[0]:.6f}" if not hist.empty else "?"
            print(f"  {m:30s}  latest={latest}")
    else:
        print("No metrics in registry.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
