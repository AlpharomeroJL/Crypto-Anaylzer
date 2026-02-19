"""Spec: RESEARCH_SPEC_VERSION, spec_summary, validate_research_only_boundary (no false positive on repo)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from crypto_analyzer.spec import RESEARCH_SPEC_VERSION, spec_summary, validate_research_only_boundary


def test_research_spec_version():
    assert isinstance(RESEARCH_SPEC_VERSION, str)
    assert RESEARCH_SPEC_VERSION >= "5.0"


def test_spec_summary_has_version():
    d = spec_summary()
    assert "research_spec_version" in d
    assert d["research_spec_version"] == RESEARCH_SPEC_VERSION


def test_validate_research_only_boundary_passes_on_repo():
    """Should not raise on this repo (no forbidden keywords in code)."""
    try:
        validate_research_only_boundary()
    except RuntimeError as e:
        pytest.fail(f"Boundary check should not fail on repo: {e}")


def test_validate_research_only_boundary_raises_on_forbidden():
    """Forbidden keyword in scanned Python source (crypto_analyzer/cli/tools) DOES fail."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "crypto_analyzer").mkdir()
        (root / "crypto_analyzer" / "bad.py").write_text("x = 'api_key'  # forbidden")
        with pytest.raises(RuntimeError, match="forbidden|api_key"):
            validate_research_only_boundary(repo_root=tmp)


def test_validate_research_only_boundary_ignores_docs():
    """Forbidden keyword in a docs file does NOT fail (docs/ not scanned)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "docs").mkdir()
        (root / "docs" / "forbidden.md").write_text("We use api_key for nothing here.")
        (root / "crypto_analyzer").mkdir()
        (root / "crypto_analyzer" / "ok.py").write_text("print('clean')")
        validate_research_only_boundary(repo_root=tmp)


def test_validate_research_only_boundary_fails_in_python_source():
    """Forbidden keyword in cli/*.py DOES fail."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "cli").mkdir()
        (root / "cli" / "script.py").write_text("submit_order()")
        with pytest.raises(RuntimeError, match="submit_order|forbidden"):
            validate_research_only_boundary(repo_root=tmp)
