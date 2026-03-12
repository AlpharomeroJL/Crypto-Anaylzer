#!/usr/bin/env python3
"""
Enforce architecture boundaries: crypto_analyzer/core must not import UI, CLI, or heavy layers.
Fails CI if core imports streamlit, plotly, or crypto_analyzer.cli/ui. Stdlib + ast only.
Only checks AST import/ImportFrom nodes (ignores comments and strings).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Core package dirs that must not import forbidden modules.
CORE_DIRS = ("crypto_analyzer/core",)
# Forbidden: top-level or dotted module names in import/from x import.
# Catches: import streamlit; from streamlit import x; from plotly.express import x; from crypto_analyzer.cli import x
FORBIDDEN = ("streamlit", "plotly", "crypto_analyzer.cli", "crypto_analyzer.ui")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _is_forbidden(module: str) -> bool:
    return any(f in module for f in FORBIDDEN)


def check_file(path: Path, root: Path) -> list[tuple[int, str]]:
    """Return list of (line_no, violation) for a single file."""
    violations = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return violations
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return violations
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden(alias.name):
                    violations.append((node.lineno, f"import {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            if node.module and _is_forbidden(node.module):
                violations.append((node.lineno, f"from {node.module} import ..."))
    return violations


def main() -> int:
    root = _repo_root()
    total = []
    for core_dir in CORE_DIRS:
        dir_path = root / core_dir
        if not dir_path.is_dir():
            continue
        for py in dir_path.rglob("*.py"):
            for line_no, msg in check_file(py, root):
                rel = py.relative_to(root)
                total.append((str(rel), line_no, msg))
    if total:
        for rel, line_no, msg in sorted(total):
            print(f"{rel}:{line_no}: core must not import UI/CLI — {msg}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
