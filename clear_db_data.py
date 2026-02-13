#!/usr/bin/env python3
"""Clear all rows from dashboard/poller SQLite tables for a fresh dataset.
Run while the poller is stopped. Then start the poller and use 'Reload data' in the dashboard.
"""
import os
import sqlite3
import sys

# Same path as dashboard and poller (when run from repo root)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "dex_data.sqlite")

SOL_MONITOR_TABLE = "sol_monitor_snapshots"
SPOT_TABLE = "spot_price_snapshots"


def main() -> None:
    if not os.path.isfile(DB_PATH):
        print(f"DB not found: {DB_PATH}")
        print("Nothing to clear. Start the poller once to create the DB, then run this to clear.")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN (?, ?)",
            (SOL_MONITOR_TABLE, SPOT_TABLE),
        )
        tables = [r[0] for r in cur.fetchall()]

        for table in [SOL_MONITOR_TABLE, SPOT_TABLE]:
            if table not in tables:
                print(f"Table {table} missing; skipping.")
                continue
            n = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
            print(f"{table}: {n} rows")
            conn.execute(f"DELETE FROM [{table}]")
            conn.commit()
            print(f"  -> cleared.")

        conn.execute("VACUUM")
        conn.commit()
        print("VACUUM done. DB is empty and ready for fresh data.")
    finally:
        conn.close()

    print("Start the poller again; use 'Reload data' in the dashboard to see only new data.")


if __name__ == "__main__":
    main()
