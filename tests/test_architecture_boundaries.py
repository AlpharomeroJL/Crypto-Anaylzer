"""
Architectural boundary tests: enforce layering (no providers in modeling, no DB in analytics, CLI does not import DB directly).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Pure modeling/analytics: no provider or DB coupling.
_MODELING_MODULES = (
    "factors",
    "portfolio",
    "optimizer",
    "risk_model",
    "evaluation",
    "walkforward",
    "alpha_research",
    "cs_model",
    "cs_factors",
    "regimes",
    "multiple_testing",
    "diagnostics",
    "signals_xs",
    "statistics",
    "features",
    "portfolio_advanced",
)

# Patterns that violate boundaries.
_PROVIDERS_IMPORT = re.compile(
    r"from\s+crypto_analyzer\.providers|from\s+\.\.?providers|import\s+crypto_analyzer\.providers"
)
_DB_IMPORT = re.compile(r"from\s+crypto_analyzer\.db|from\s+\.\.?db\.|import\s+crypto_analyzer\.db")
_SQLITE3_IMPORT = re.compile(r"import\s+sqlite3")

# Paths relative to repo root.
_CA_ROOT = _REPO_ROOT / "crypto_analyzer"
_CLI_ROOT = _REPO_ROOT / "cli"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def test_modeling_does_not_import_providers():
    """No imports from providers/ inside modeling modules."""
    violations = []
    for name in _MODELING_MODULES:
        p = _CA_ROOT / f"{name}.py"
        if not p.exists():
            continue
        text = _read_text(p)
        if _PROVIDERS_IMPORT.search(text):
            violations.append(str(p.relative_to(_REPO_ROOT)))
    assert not violations, "Modeling modules must not import from providers: " + ", ".join(violations)


def test_modeling_does_not_import_db_or_sqlite3():
    """No DB access from analytics/modeling layer."""
    violations = []
    for name in _MODELING_MODULES:
        p = _CA_ROOT / f"{name}.py"
        if not p.exists():
            continue
        text = _read_text(p)
        if _DB_IMPORT.search(text) or _SQLITE3_IMPORT.search(text):
            violations.append(str(p.relative_to(_REPO_ROOT)))
    assert not violations, "Modeling modules must not import crypto_analyzer.db or sqlite3: " + ", ".join(violations)


def test_cli_does_not_import_db_directly():
    """CLI must not import DB layer directly (use package API instead)."""
    violations = []
    if not _CLI_ROOT.is_dir():
        pytest.skip("No cli/ directory")
    for path in _CLI_ROOT.glob("*.py"):
        text = _read_text(path)
        if _DB_IMPORT.search(text):
            violations.append(str(path.relative_to(_REPO_ROOT)))
    assert not violations, "CLI scripts must not import crypto_analyzer.db directly: " + ", ".join(violations)
