"""Config DB path: relative entries resolve to repo root (stable across cwd)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from crypto_analyzer.config import _repo_root, resolve_config_db_path


def test_resolve_relative_db_path_anchors_to_repo_root() -> None:
    root = _repo_root()
    resolved = resolve_config_db_path("dex_data.sqlite")
    assert Path(resolved).is_absolute()
    assert resolved == str((root / "dex_data.sqlite").resolve())


def test_resolve_absolute_db_path_unchanged_parent() -> None:
    abs_path = str(Path(tempfile.gettempdir()) / "abs_test_crypto_analyzer.sqlite")
    resolved = resolve_config_db_path(abs_path)
    assert Path(resolved).resolve() == Path(abs_path).resolve()


def test_resolve_memory_and_empty() -> None:
    assert resolve_config_db_path(":memory:") == ":memory:"
    assert resolve_config_db_path("") == ""
