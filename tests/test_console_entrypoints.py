"""Verify CLI modules expose a main() callable without executing them."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_CLI_DIR = Path(__file__).resolve().parent.parent / "cli"

_CLI_MODULES = [
    "app",
    "scan",
    "research_report_v2",
    "api",
    "materialize",
    "poll",
]


@pytest.mark.parametrize("name", _CLI_MODULES)
def test_cli_module_has_main(name):
    path = _CLI_DIR / f"{name}.py"
    assert path.exists(), f"cli/{name}.py not found"
    spec = importlib.util.spec_from_file_location(f"cli.{name}", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "main"), f"cli/{name}.py missing main()"
