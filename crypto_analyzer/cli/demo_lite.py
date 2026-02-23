"""
Demo-lite: generate a small synthetic dataset into the DB (no network).
For offline onboarding: init -> demo-lite -> check-dataset.
Runs under network guard when CRYPTO_ANALYZER_NO_NETWORK=1.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    ap = argparse.ArgumentParser(
        prog="crypto-analyzer demo-lite",
        description="Generate synthetic dataset (no network). Run after init.",
    )
    ap.add_argument(
        "--db",
        default="data/crypto_analyzer.sqlite",
        help="DB path (default: data/crypto_analyzer.sqlite)",
    )
    args = ap.parse_args(argv)
    db_path = Path(args.db)
    if not db_path.is_absolute():
        root = Path(__file__).resolve().parents[2]
        db_path = root / db_path
    db_path = db_path.resolve()
    path_str = str(db_path)
    if not db_path.exists():
        print(f"DB not found: {path_str}. Run: crypto-analyzer init [--db ...]", file=sys.stderr)
        return 1

    def _run() -> int:
        # Deterministic synthetic data (no network)
        with sqlite3.connect(path_str) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO spot_price_snapshots (ts_utc, symbol, spot_price_usd, spot_source)
                VALUES
                    ('2020-01-01T00:00:00', 'BTC', 50000.0, 'demo-lite'),
                    ('2020-01-01T01:00:00', 'BTC', 50100.0, 'demo-lite'),
                    ('2020-01-01T02:00:00', 'BTC', 49900.0, 'demo-lite'),
                    ('2020-01-01T00:00:00', 'ETH', 3000.0, 'demo-lite'),
                    ('2020-01-01T01:00:00', 'ETH', 3020.0, 'demo-lite')
                """
            )
            conn.commit()
        print("demo-lite: synthetic spot_price_snapshots inserted (deterministic).")
        return 0

    use_guard = os.environ.get("CRYPTO_ANALYZER_NO_NETWORK") == "1"
    if use_guard:
        from crypto_analyzer.cli.smoke import network_guard

        with network_guard():
            return _run()
    return _run()
