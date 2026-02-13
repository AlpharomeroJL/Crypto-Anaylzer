#!/usr/bin/env python3
"""Clear all rows from dashboard/poller SQLite tables for a fresh dataset.

Historical graph data is only cleared when you run this script with --yes.
The dashboard has no clear/delete button so you cannot accidentally wipe data from the UI.

Usage:
  python clear_db_data.py          # Dry run: show row counts, do nothing.
  python clear_db_data.py --yes    # Permanently delete all table data (run with poller stopped).
"""
import argparse
import os
import sqlite3
import sys

# Same path as dashboard and poller (when run from repo root)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "dex_data.sqlite")

SOL_MONITOR_TABLE = "sol_monitor_snapshots"
SPOT_TABLE = "spot_price_snapshots"


def main() -> None:
    parser = argparse.ArgumentParser(description="Clear all table data (requires --yes to confirm).")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm: permanently delete all historical data from the DB.",
    )
    args = parser.parse_args()

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

        total = 0
        for table in [SOL_MONITOR_TABLE, SPOT_TABLE]:
            if table not in tables:
                print(f"Table {table} missing; skipping.")
                continue
            n = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
            print(f"{table}: {n} rows")
            total += n

        if total == 0:
            print("No data to clear.")
            return

        if not args.yes:
            print("")
            print("This would PERMANENTLY delete all historical data from the database.")
            print("To clear, run:  python clear_db_data.py --yes")
            print("(Stop the poller first, then start it again after clearing.)")
            return

        print("")
        print("Clearing all rows...")
        for table in [SOL_MONITOR_TABLE, SPOT_TABLE]:
            if table not in tables:
                continue
            conn.execute(f"DELETE FROM [{table}]")
            conn.commit()
            print(f"  {table}: cleared.")

        conn.execute("VACUUM")
        conn.commit()
        print("VACUUM done. DB is empty and ready for fresh data.")
        print("Start the poller again; refresh the dashboard (F5) to see only new data.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
