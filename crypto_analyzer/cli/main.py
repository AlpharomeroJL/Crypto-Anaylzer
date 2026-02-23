"""
Top-level CLI dispatcher: crypto-analyzer <command> [args...].
All commands dispatch to package CLI modules or doctor.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import List, Optional


def _main_doctor(argv: List[str]) -> int:
    from crypto_analyzer.doctor import main as doctor_main

    return doctor_main(argv)


def _main_verify(argv: List[str]) -> int:
    from crypto_analyzer.doctor import main as doctor_main

    if doctor_main() != 0:
        return 1
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/"] + argv, cwd=None)
    if r.returncode != 0:
        return r.returncode
    r = subprocess.run([sys.executable, "-m", "ruff", "check", "."], cwd=None)
    if r.returncode != 0:
        return r.returncode
    r = subprocess.run(
        [
            sys.executable,
            "-c",
            "from crypto_analyzer.spec import validate_research_only_boundary; validate_research_only_boundary()",
        ],
        cwd=None,
    )
    if r.returncode != 0:
        return r.returncode
    return 0


def _main_test(argv: List[str]) -> int:
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/"] + argv, cwd=None)
    return r.returncode


def _main_streamlit(argv: List[str]) -> int:
    from pathlib import Path

    app_path = Path(__file__).resolve().parent / "app.py"
    r = subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path)] + argv, cwd=None)
    return r.returncode


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="crypto-analyzer",
        description="Crypto quantitative research platform CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="command")
    for name in (
        "doctor",
        "smoke",
        "init",
        "demo-lite",
        "poll",
        "universe-poll",
        "materialize",
        "report",
        "reportv2",
        "walkforward",
        "promotion",
        "verify",
        "test",
        "streamlit",
        "demo",
        "check-dataset",
        "analyze",
        "scan",
        "daily",
        "backtest",
        "api",
        "null_suite",
        "audit_trace",
        "dashboard",
    ):
        subparsers.add_parser(name, help=f"Run {name}")

    args, rest = parser.parse_known_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    cmd = args.command

    if cmd == "doctor":
        return _main_doctor(rest)
    if cmd == "smoke":
        from crypto_analyzer.cli import smoke as smoke_mod

        return smoke_mod.main(rest)
    if cmd == "init":
        from crypto_analyzer.cli import init_db as mod

        return mod.main(rest)
    if cmd == "demo-lite":
        from crypto_analyzer.cli import demo_lite as mod

        return mod.main(rest)
    if cmd == "verify":
        return _main_verify(rest)
    if cmd == "test":
        return _main_test(rest)
    if cmd == "streamlit":
        return _main_streamlit(rest)

    if cmd == "poll":
        from crypto_analyzer.cli import poll as poll_mod

        return poll_mod.main(rest)
    if cmd == "universe-poll":
        from crypto_analyzer.cli import poll as poll_mod

        return poll_mod.main(["--universe"] + rest)
    if cmd == "materialize":
        from crypto_analyzer.cli import materialize as mod

        return mod.main(rest)
    if cmd == "report":
        from crypto_analyzer.cli import report as mod

        return mod.main(rest)
    if cmd == "reportv2":
        from crypto_analyzer.cli import reportv2 as mod

        return mod.main(rest)
    if cmd == "walkforward":
        from crypto_analyzer.cli import walkforward as mod

        return mod.main(rest)
    if cmd == "promotion":
        from crypto_analyzer.cli import promotion as mod

        return mod.main(rest)
    if cmd == "demo":
        from crypto_analyzer.cli import demo as mod

        return mod.main(rest)
    if cmd == "check-dataset":
        from crypto_analyzer.cli import check_dataset as mod

        return mod.main(rest)
    if cmd == "analyze":
        from crypto_analyzer.cli import analyze as mod

        return mod.main(rest)
    if cmd == "scan":
        from crypto_analyzer.cli import scan as mod

        return mod.main(rest)
    if cmd == "daily":
        from crypto_analyzer.cli import daily as mod

        return mod.main(rest)
    if cmd == "backtest":
        from crypto_analyzer.cli import backtest as mod

        return mod.main(rest)
    if cmd == "api":
        from crypto_analyzer.cli import api as mod

        return mod.main(rest)
    if cmd == "null_suite":
        from crypto_analyzer.cli import null_suite as mod

        return mod.main(rest)
    if cmd == "audit_trace":
        from crypto_analyzer.cli import audit_trace as mod

        return mod.main(rest)
    if cmd == "dashboard":
        from crypto_analyzer.cli import dashboard as mod

        return mod.main(rest)

    parser.print_help()
    return 0
