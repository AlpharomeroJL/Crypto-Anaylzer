"""
System health check: run critical commands and generate a structured report.
Inspection only; does not modify project logic.
"""
from __future__ import annotations

import os
import platform
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Tables we care about for row counts
BAR_TABLES = ["bars_5min", "bars_15min", "bars_1h", "bars_1D"]
OTHER_TABLES = ["sol_monitor_snapshots", "spot_price_snapshots"]
ALL_COUNT_TABLES = BAR_TABLES + OTHER_TABLES

# Critical CLI commands: (name, [argv])
CRITICAL_COMMANDS = [
    ("cli/materialize.py", [sys.executable, "cli/materialize.py"]),
    ("cli/analyze.py --freq 1h --window 24", [sys.executable, "cli/analyze.py", "--freq", "1h", "--window", "24"]),
    ("cli/scan.py --mode momentum --freq 1h --top 5", [sys.executable, "cli/scan.py", "--mode", "momentum", "--freq", "1h", "--top", "5"]),
    ("cli/report_daily.py", [sys.executable, "cli/report_daily.py"]),
    ("cli/research_report.py --freq 1h", [sys.executable, "cli/research_report.py", "--freq", "1h"]),
    ("cli/research_report_v2.py --freq 1h", [sys.executable, "cli/research_report_v2.py", "--freq", "1h"]),
    ("pytest tests/ -q", [sys.executable, "-m", "pytest", "tests/", "-q"]),
]

STDOUT_LINES = 20


def get_db_path() -> str:
    """Resolve DB path from config; relative paths against repo root."""
    try:
        from crypto_analyzer.config import db_path as _db_path
        raw = _db_path() if callable(_db_path) else _db_path
    except Exception:
        raw = "dex_data.sqlite"
    if os.path.isabs(raw):
        return raw
    return str(REPO_ROOT / raw)


def collect_environment() -> dict:
    """Collect environment metadata."""
    out = {
        "python_version": sys.version,
        "sys_executable": sys.executable,
        "platform": platform.platform(),
        "sys_path_first_3": list(sys.path[:3]),
    }
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=10,
        )
        out["pip_version"] = (r.stdout or r.stderr or "").strip() if (r.returncode == 0 or r.stdout or r.stderr) else "unknown"
    except Exception:
        out["pip_version"] = "unknown"
    return out


def check_database(db_path: str) -> tuple[dict, list[str]]:
    """
    Check DB existence, list tables, count rows. Return (info_dict, warnings).
    """
    info = {"exists": False, "tables": [], "row_counts": {}, "error": None}
    warnings = []

    if not os.path.isfile(db_path):
        info["error"] = f"Database not found: {db_path}"
        warnings.append(info["error"])
        return info, warnings

    info["exists"] = True
    try:
        with sqlite3.connect(db_path) as con:
            cur = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            info["tables"] = [row[0] for row in cur.fetchall()]
            for table in ALL_COUNT_TABLES:
                if table not in info["tables"]:
                    info["row_counts"][table] = None
                    if table in BAR_TABLES:
                        warnings.append(f"Bars table missing: {table}")
                else:
                    try:
                        cur = con.execute(f"SELECT COUNT(*) FROM [{table}]")
                        info["row_counts"][table] = cur.fetchone()[0]
                        if table in BAR_TABLES and info["row_counts"][table] == 0:
                            warnings.append(f"Bars table has 0 rows: {table}")
                    except Exception as e:
                        info["row_counts"][table] = None
                        warnings.append(f"Count failed for {table}: {e}")
    except Exception as e:
        info["error"] = str(e)
        warnings.append(f"Database error: {e}")

    return info, warnings


def run_command(name: str, argv: list[str]) -> dict:
    """Run one command; capture return code, first N lines of stdout, stderr; time it."""
    result = {
        "name": name,
        "return_code": None,
        "stdout_first_lines": [],
        "stderr": "",
        "status": "FAIL",
        "duration_sec": None,
        "error": None,
    }
    start = time.perf_counter()
    try:
        r = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=300,
        )
        result["return_code"] = r.returncode
        result["stdout_first_lines"] = (r.stdout or "").splitlines()[:STDOUT_LINES]
        result["stderr"] = (r.stderr or "").strip()
        result["status"] = "PASS" if r.returncode == 0 else "FAIL"
    except subprocess.TimeoutExpired:
        result["error"] = "timeout"
        result["status"] = "FAIL"
    except FileNotFoundError as e:
        result["error"] = f"command not found: {e}"
        result["status"] = "FAIL"
    except Exception as e:
        result["error"] = str(e)
        result["status"] = "FAIL"
    result["duration_sec"] = round(time.perf_counter() - start, 2)
    return result


def streamlit_import_check() -> tuple[str, str | None]:
    """Try importing streamlit and crypto_analyzer. Return (status, error_message)."""
    try:
        import streamlit  # noqa: F401
    except Exception as e:
        return "FAIL", f"import streamlit: {e}"
    try:
        import crypto_analyzer  # noqa: F401
    except Exception as e:
        return "FAIL", f"import crypto_analyzer: {e}"
    return "PASS", None


def build_report(
    env: dict,
    db_info: dict,
    db_warnings: list[str],
    cli_results: list[dict],
    streamlit_status: str,
    streamlit_error: str | None,
    all_warnings: list[str],
    timestamp_utc: str,
) -> str:
    """Build markdown report content."""
    lines = [
        "# System Health Report",
        f"Generated: {timestamp_utc} (UTC)",
        "",
        "## Environment",
        f"- Python: {env.get('python_version', '')}",
        f"- sys.executable: {env.get('sys_executable', '')}",
        f"- pip: {env.get('pip_version', '')}",
        f"- platform: {env.get('platform', '')}",
        f"- sys.path (first 3): {env.get('sys_path_first_3', [])}",
        "",
        "## Database",
        f"- Path: {db_info.get('path', 'N/A')}",
        f"- Exists: {db_info.get('exists', False)}",
        f"- Tables: {db_info.get('tables', [])}",
        "- Row counts:",
    ]
    for table, count in (db_info.get("row_counts") or {}).items():
        lines.append(f"  - {table}: {count}")
    if db_info.get("error"):
        lines.append(f"- Error: {db_info['error']}")

    lines.extend([
        "",
        "## CLI Results",
        "",
    ])
    for r in cli_results:
        lines.append(f"### {r['name']}")
        lines.append(f"- Status: **{r['status']}** | return code: {r.get('return_code', 'N/A')} | duration: {r.get('duration_sec')}s")
        if r.get("error"):
            lines.append(f"- Error: {r['error']}")
        if r.get("stderr"):
            lines.append(f"- stderr: {r['stderr'][:500]}{'...' if len(r.get('stderr', '')) > 500 else ''}")
        lines.append("- stdout (first lines):")
        for ln in r.get("stdout_first_lines") or []:
            lines.append(f"  {ln}")
        lines.append("")

    lines.extend([
        "## Streamlit import",
        f"- Status: **{streamlit_status}**",
        "",
        "## Test Results",
        "",
    ])
    pytest_result = next((x for x in cli_results if "pytest" in x["name"]), None)
    if pytest_result:
        lines.append(f"- Status: **{pytest_result['status']}** (return code {pytest_result.get('return_code')})")
        for ln in pytest_result.get("stdout_first_lines") or []:
            lines.append(f"  {ln}")
    else:
        lines.append("- (pytest not run or not in CLI results)")
    lines.append("")

    lines.extend([
        "## Warnings",
        "",
    ])
    if all_warnings:
        for w in all_warnings:
            lines.append(f"- {w}")
    else:
        lines.append("- None")

    return "\n".join(lines)


def main() -> int:
    timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    all_warnings: list[str] = []

    # 1) Environment
    env = collect_environment()

    # 2) Database
    db_path = get_db_path()
    db_info, db_warnings = check_database(db_path)
    db_info["path"] = db_path
    all_warnings.extend(db_warnings)

    # 3) Critical commands
    cli_results = []
    for name, argv in CRITICAL_COMMANDS:
        res = run_command(name, argv)
        cli_results.append(res)
        if res["status"] == "FAIL":
            all_warnings.append(f"Command failed: {name} (code={res.get('return_code')}, error={res.get('error')})")

    # 4) Streamlit import
    streamlit_status, streamlit_error = streamlit_import_check()
    if streamlit_error:
        all_warnings.append(f"Streamlit import: {streamlit_error}")

    # 5) Report file
    reports_dir = REPO_ROOT / "reports"
    try:
        reports_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    report_path = reports_dir / f"system_health_{timestamp_utc}.md"
    report_content = build_report(
        env, db_info, db_warnings, cli_results,
        streamlit_status, streamlit_error, all_warnings, timestamp_utc,
    )
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)
    except Exception as e:
        all_warnings.append(f"Could not write report: {e}")

    # 6) Console summary
    cli_pass = all(r["status"] == "PASS" for r in cli_results)
    db_ok = db_info.get("exists") and not db_info.get("error")
    bars_ok = not any(
        db_info.get("row_counts", {}).get(t) == 0 for t in BAR_TABLES
        if db_info.get("row_counts", {}).get(t) is not None
    )
    streamlit_ok = streamlit_status == "PASS"
    overall = cli_pass and streamlit_ok

    if overall:
        print("sanity_check: PASS (all critical commands and imports OK)")
    else:
        print("sanity_check: FAIL")
        failed = [r["name"] for r in cli_results if r["status"] == "FAIL"]
        if failed:
            print("  Failed commands:", ", ".join(failed))
        if streamlit_status != "PASS":
            print("  Streamlit import: FAIL")
    if all_warnings:
        print("  Warnings:", len(all_warnings))
    print(f"  Report: {report_path}")

    # 7) Exit code
    return 0 if overall else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"sanity_check error: {e}", file=sys.stderr)
        sys.exit(1)
