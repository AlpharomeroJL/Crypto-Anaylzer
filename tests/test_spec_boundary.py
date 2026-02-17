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
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "bad.py").write_text("x = 'api_key'  # forbidden")
        with pytest.raises(RuntimeError, match="forbidden|api_key"):
            validate_research_only_boundary(repo_root=tmp)
