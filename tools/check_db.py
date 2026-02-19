#!/usr/bin/env python3
"""Quick sanity check for dex_data.sqlite: tables and spot_price_snapshots row count."""

import sqlite3

DB_PATH = "dex_data.sqlite"
conn = sqlite3.connect(DB_PATH)
tables = [r[0] for r in conn.execute("select name from sqlite_master where type='table'").fetchall()]
print("tables:", tables)

if "spot_price_snapshots" in tables:
    n = conn.execute("select count(*) from spot_price_snapshots").fetchone()[0]
    print("spot rows:", n)
else:
    print("spot rows: no table")

conn.close()
