"""
Phase 3 A1: Enforce package boundaries (core, governance, store, plugins, cli).
- core cannot import governance, store, cli
- governance cannot import cli
- store cannot import core modules that contain business logic (only persistence primitives)
- cli imports must be top-level adapters only
"""

from __future__ import annotations

import ast
from pathlib import Path


def _collect_imports_from_file(path: Path) -> list[tuple[str, int]]:
    """Return list of (module_name, line_no) for each import from crypto_analyzer.* or cli.*."""
    imports = []
    try:
        src = path.read_text(encoding="utf-8")
    except Exception:
        return []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            if node.module.startswith("crypto_analyzer.") or node.module.startswith("cli."):
                imports.append((node.module, node.lineno))
    return imports


def test_core_cannot_import_governance_store_cli():
    """Core must not import from governance, store, or cli."""
    root = Path(__file__).resolve().parent.parent
    core_dir = root / "crypto_analyzer" / "core"
    if not core_dir.is_dir():
        return
    for path in core_dir.rglob("*.py"):
        if path.name.startswith("_"):
            continue
        for mod, line in _collect_imports_from_file(path):
            if (
                mod.startswith("crypto_analyzer.governance")
                or mod.startswith("crypto_analyzer.store")
                or mod.startswith("cli.")
            ):
                raise AssertionError(
                    f"core must not import governance/store/cli: {path.relative_to(root)} line {line} imports {mod}"
                )


def test_governance_cannot_import_cli():
    """Governance must not import cli."""
    root = Path(__file__).resolve().parent.parent
    gov_dir = root / "crypto_analyzer" / "governance"
    if not gov_dir.is_dir():
        return
    for path in gov_dir.rglob("*.py"):
        for mod, line in _collect_imports_from_file(path):
            if mod.startswith("cli."):
                raise AssertionError(
                    f"governance must not import cli: {path.relative_to(root)} line {line} imports {mod}"
                )


def test_store_cannot_import_core_business_logic():
    """Store must not import core modules that contain business logic (e.g. promotion gating, validation)."""
    root = Path(__file__).resolve().parent.parent
    store_dir = root / "crypto_analyzer" / "store"
    if not store_dir.is_dir():
        return
    # Store may import db.lineage, db.governance_events (persistence); must not import core.*, promotion.gating, etc.
    forbidden = ("crypto_analyzer.core", "crypto_analyzer.promotion.gating", "crypto_analyzer.promotion.service")
    for path in store_dir.rglob("*.py"):
        for mod, line in _collect_imports_from_file(path):
            for prefix in forbidden:
                if mod.startswith(prefix) or mod == prefix:
                    raise AssertionError(
                        f"store must not import business logic: {path.relative_to(root)} line {line} imports {mod}"
                    )


def test_db_cannot_import_governance():
    """DB (store-layer persistence) must not import governance (run identity lives in core)."""
    root = Path(__file__).resolve().parent.parent
    db_dir = root / "crypto_analyzer" / "db"
    if not db_dir.is_dir():
        return
    for path in db_dir.rglob("*.py"):
        if path.name.startswith("_"):
            continue
        for mod, line in _collect_imports_from_file(path):
            if mod.startswith("crypto_analyzer.governance"):
                raise AssertionError(
                    f"db must not import governance: {path.relative_to(root)} line {line} imports {mod}"
                )


# Legacy module paths that must not appear as import targets (Phase 3.5 A6). Add when removing modules.
FORBIDDEN_IMPORT_STRINGS: list[str] = []


def test_no_forbidden_import_strings():
    """No file under crypto_analyzer/ or cli/ may use forbidden import patterns (legacy/removed modules)."""
    root = Path(__file__).resolve().parent.parent
    for dir_name in ("crypto_analyzer", "cli"):
        dir_path = root / dir_name
        if not dir_path.is_dir():
            continue
        for path in dir_path.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            for forbidden in FORBIDDEN_IMPORT_STRINGS:
                if forbidden in text:
                    raise AssertionError(f"Forbidden import pattern {forbidden!r} found in {path.relative_to(root)}")
