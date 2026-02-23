"""Verify CLI modules expose main() and crypto-analyzer --help works."""

from __future__ import annotations

import subprocess
import sys
from importlib import import_module

import pytest

_CLI_MODULES = [
    "crypto_analyzer.cli.poll",
    "crypto_analyzer.cli.materialize",
    "crypto_analyzer.cli.reportv2",
    "crypto_analyzer.cli.report",
    "crypto_analyzer.cli.promotion",
    "crypto_analyzer.cli.demo",
    "crypto_analyzer.cli.analyze",
    "crypto_analyzer.cli.scan",
    "crypto_analyzer.cli.api",
    "crypto_analyzer.cli.backtest",
    "crypto_analyzer.cli.walkforward",
    "crypto_analyzer.cli.daily",
    "crypto_analyzer.cli.null_suite",
    "crypto_analyzer.cli.audit_trace",
    "crypto_analyzer.cli.check_dataset",
]


@pytest.mark.parametrize("module_name", _CLI_MODULES)
def test_cli_module_has_main(module_name):
    mod = import_module(module_name)
    assert hasattr(mod, "main"), f"{module_name} missing main()"
    assert callable(mod.main), f"{module_name}.main not callable"


def test_cli_main_help_exits_zero():
    """cli.main.main(["--help"]) exits with 0 (in-process)."""
    from crypto_analyzer.cli.main import main

    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0


def test_crypto_analyzer_help_exits_zero():
    """python -m crypto_analyzer --help exits 0 and lists commands (subprocess)."""
    r = subprocess.run(
        [sys.executable, "-m", "crypto_analyzer", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    out = (r.stdout or "") + (r.stderr or "")
    assert "doctor" in out, "Help output should list 'doctor' command"
