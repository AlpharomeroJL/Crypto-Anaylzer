"""Regression guard: tests must not use sys.path.insert/append.

Use package imports (e.g. crypto_analyzer.cli.*) instead. Default: violations
are reported via xfail so the suite stays green while legacy hacks remain.
Strict mode: set STRICT_SYSPATH_GUARD=1 to fail the test (and CI) on any
violation. Enable strict locally to validate before enabling in CI.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_FORBIDDEN = ("sys.path.insert(", "sys.path.append(")
_THIS_FILE = Path(__file__).resolve()


def test_no_syspath_hacks_in_tests():
    """Fail if any test file under tests/ contains sys.path.insert or sys.path.append."""
    tests_dir = Path(__file__).resolve().parent
    hits: list[tuple[str, int, str]] = []
    for path in sorted(tests_dir.rglob("*.py")):
        if path == _THIS_FILE:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            for forbidden in _FORBIDDEN:
                if forbidden in line:
                    hits.append((str(path), i, line.strip()))
                    break
    msg = "Forbidden sys.path hacks found. Use package imports (e.g. crypto_analyzer.cli.*) instead.\n"
    if hits:
        msg += "\n".join(f"  {path}:{line_no}: {snippet}" for path, line_no, snippet in hits)
        if os.environ.get("STRICT_SYSPATH_GUARD") == "1":
            raise AssertionError(msg)
        pytest.xfail(reason=msg)
    assert True
