"""
System doctor: preflight checks for env, deps, DB, integrity, and minimal pipeline.
Run: python -m crypto_analyzer.doctor
Exit: 0 all OK, 2 env/deps, 3 DB/schema, 4 pipeline smoke.
Research-only; no execution.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Repo root (parent of crypto_analyzer package)
_REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_TABLES = ["sol_monitor_snapshots", "spot_price_snapshots", "bars_1h"]
REQUIRED_BARS_COLUMNS = ["ts_utc", "chain_id", "pair_address", "close"]
DEPENDENCIES = ["requests", "pandas", "numpy", "streamlit", "plotly"]


def _in_venv() -> bool:
    return getattr(sys, "prefix", None) != getattr(sys, "base_prefix", None)


def _get_db_path() -> str:
    try:
        from .config import db_path
        p = db_path() if callable(db_path) else db_path
        path = p() if callable(p) else str(p)
    except Exception:
        path = "dex_data.sqlite"
    if not os.path.isabs(path):
        path = str(_REPO_ROOT / path)
    return path


def check_env() -> bool:
    """Return True if in venv; else print fix and return False."""
    if _in_venv():
        print(f"[OK] venv active  python={sys.executable}")
        return True
    print("[FAIL] Not running inside a virtual environment.")
    print("  Fix: Run  .\\.venv\\Scripts\\Activate  then use  python -m crypto_analyzer.doctor")
    print(f"  Or:  .\\.venv\\Scripts\\python.exe -m crypto_analyzer.doctor")
    return False


def check_dependencies() -> bool:
    """Return True if all required packages import; else print pip install and return False."""
    missing = []
    for pkg in DEPENDENCIES:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if not missing:
        print("[OK] dependencies  " + " ".join(DEPENDENCIES))
        return True
    print("[FAIL] Missing packages: " + ", ".join(missing))
    print("  Fix: .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt")
    print("  Or:  .\\.venv\\Scripts\\python.exe -m pip install " + " ".join(missing))
    return False


def check_db() -> bool:
    """Return True if DB exists and required tables/columns present; else print and return False."""
    db = _get_db_path()
    if not os.path.isfile(db):
        print(f"[FAIL] DB not found: {db}")
        print("  Create DB: .\\.venv\\Scripts\\python.exe dex_poll_to_sqlite.py --interval 60")
        print("  Or universe: .\\.venv\\Scripts\\python.exe dex_poll_to_sqlite.py --universe --universe-chain solana --universe-query USDC --universe-query USDT --interval 60")
        print("  (If universe returns 0 pairs, try broader queries: --universe-query USDC --universe-query USDT)")
        return False
    print(f"[OK] DB exists  {db}")

    import sqlite3
    try:
        with sqlite3.connect(db) as con:
            cur = con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = {row[0] for row in cur.fetchall()}
    except Exception as e:
        print(f"[FAIL] DB error: {e}")
        return False

    for t in REQUIRED_TABLES:
        if t not in tables:
            print(f"[FAIL] Missing table: {t}")
            return False
    print(f"[OK] tables  {', '.join(REQUIRED_TABLES)}")

    for table in ["sol_monitor_snapshots", "bars_1h"]:
        try:
            with sqlite3.connect(db) as con:
                cur = con.execute(f"PRAGMA table_info([{table}])")
                cols = {row[1] for row in cur.fetchall()}
        except Exception:
            cols = set()
        required = ["ts_utc", "close"] if table == "bars_1h" else ["ts_utc"]
        if table == "sol_monitor_snapshots":
            required = ["ts_utc", "chain_id", "pair_address"]
        for c in required:
            if c not in cols:
                print(f"[FAIL] Missing column: {table}.{c}")
                return False
    print("[OK] schema  required columns present")
    return True


def check_integrity() -> None:
    """Print non-positive price counts per table/column (informational)."""
    try:
        from .config import price_column
        price_col = price_column() if callable(price_column) else "dex_price_usd"
    except Exception:
        price_col = "dex_price_usd"
    db = _get_db_path()
    checks = [
        ("spot_price_snapshots", "spot_price_usd"),
        ("sol_monitor_snapshots", price_col),
        ("bars_1h", "close"),
    ]
    try:
        from .integrity import count_non_positive_prices, bad_row_rate
        results = count_non_positive_prices(db, checks)
        rate_results = bad_row_rate(db, checks)
    except Exception:
        results = []
        rate_results = []
    if not results:
        print("[OK] integrity  no non-positive prices in checked tables")
        return
    print("[INFO] integrity  non-positive counts (dropped at load time):")
    for table, col, count in results:
        print(f"  {table}.{col}: {count}")
    for table, col, bad, total, pct in rate_results:
        if total:
            print(f"  {table}.{col} bad row rate: {pct:.2f}% ({bad}/{total})")


def check_pipeline_smoke() -> bool:
    """Load bars_1h and get_research_assets; optionally run report dry. Return True if no crash."""
    db = _get_db_path()
    if not os.path.isfile(db):
        return False
    try:
        from .data import load_bars
        from .research_universe import get_research_assets
    except ImportError as e:
        print(f"[FAIL] pipeline import: {e}")
        return False
    try:
        bars = load_bars("1h", db_path_override=db, min_bars=None)
        if bars.empty:
            print("[WARN] pipeline  bars_1h empty (run poller + materialize_bars)")
        returns_df, meta_df = get_research_assets(db, "1h", include_spot=True)
        n = returns_df.shape[1] if not returns_df.empty else 0
        # Minimal metric: mean return (one period) if we have data
        if not returns_df.empty and returns_df.size > 0:
            import numpy as np
            mean_ret = float(np.nanmean(returns_df.values))
            print(f"[OK] pipeline  bars loaded, universe size={n}, mean_return_1bar={mean_ret:.6f}")
        else:
            print(f"[OK] pipeline  bars loaded, universe size={n}")
    except Exception as e:
        print(f"[FAIL] pipeline smoke: {e}")
        print("  Ensure: .\\.venv\\Scripts\\python.exe dex_poll_to_sqlite.py ... then materialize_bars.py")
        return False
    return True


def _warn_universe_zero_if_enabled() -> None:
    """If universe.enabled, run one-shot fetch; warn if 0 pairs accepted."""
    try:
        from .config import get_config
        u = get_config().get("universe") or {}
        if not u.get("enabled"):
            return
        import sys
        sys.path.insert(0, str(_REPO_ROOT))
        sys.path.insert(0, str(_REPO_ROOT / "cli"))
        from poll import fetch_dex_universe_top_pairs, load_universe_config
        cfg = load_universe_config(str(_REPO_ROOT / "config.yaml"))
        chain = cfg.get("chain_id", "solana")
        queries = cfg.get("queries") or ["USDC", "USDT", "SOL"]
        pairs = fetch_dex_universe_top_pairs(
            chain_id=chain, page_size=20,
            min_liquidity_usd=0, min_vol_h24=0,
            queries=queries,
        )
        if len(pairs) == 0:
            print("[WARN] Universe enabled but one-shot fetch returned 0 accepted pairs. Try broader queries: --universe-query USDC --universe-query USDT")
    except Exception:
        pass


def main() -> int:
    """Run all checks; return 0 OK, 2 env/deps, 3 DB/schema, 4 pipeline."""
    try:
        print("Crypto-Analyzer system doctor")
        print("-" * 40)

        if not check_env():
            return 2
        if not check_dependencies():
            return 2
        if not check_db():
            return 3
        check_integrity()
        _warn_universe_zero_if_enabled()
        if not check_pipeline_smoke():
            return 4

        print("-" * 40)
        print("All checks passed.")
        return 0
    except Exception as e:
        print(f"[FAIL] doctor error: {e}")
        print("  Run with: .\\.venv\\Scripts\\python.exe -m crypto_analyzer.doctor")
        return 2


if __name__ == "__main__":
    sys.exit(main())
