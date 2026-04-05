"""Tests for GrapeRoot .graperootignore parsing (no graperoot package required)."""

from __future__ import annotations

from pathlib import Path

from tools.graperoot_ignore import DEFAULT_GRAPEROOT_EXCLUDES, parse_graperootignore


def test_parse_graperootignore_repo_file_contains_claude_and_reports() -> None:
    root = Path(__file__).resolve().parents[1]
    names = parse_graperootignore(root)
    assert ".claude" in names
    assert "reports" in names
    assert "graphviz" in names


def test_defaults_include_core_noise_dirs() -> None:
    assert ".claude" in DEFAULT_GRAPEROOT_EXCLUDES
    assert "reports" in DEFAULT_GRAPEROOT_EXCLUDES


def test_parse_empty_custom_file_falls_back_to_defaults(tmp_path: Path) -> None:
    (tmp_path / ".graperootignore").write_text("# only comments\n\n", encoding="utf-8")
    names = parse_graperootignore(tmp_path)
    assert names == DEFAULT_GRAPEROOT_EXCLUDES
