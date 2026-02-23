"""
Promotion layer boundary tests: gating stays pure (no I/O/resolver/store/CLI imports),
service uses evidence_resolver. No reliance on PATH or global crypto-analyzer install.
"""

from __future__ import annotations

import ast
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Gating must not import these (denylist: pathlib, importlib, file I/O, sqlite store, evidence resolver, CLI).
GATING_IMPORT_DENYLIST = {
    "pathlib",
    "importlib",
    "sqlite3",
    "os",
    "crypto_analyzer.promotion.evidence_resolver",
    "crypto_analyzer.promotion.store_sqlite",
    "crypto_analyzer.cli",
}


def _gating_source_path() -> Path:
    return Path(__file__).resolve().parent.parent / "crypto_analyzer" / "promotion" / "gating.py"


def _imported_modules_from_source(path: Path) -> set[str]:
    """Return set of module names imported in path (full names: import x; from x.y import z -> x, x.y)."""
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
                modules.add(node.module.split(".")[0])
    return modules


def _type_checking_imports_from_source(path: Path) -> set[str]:
    """Return set of module names imported inside 'if TYPE_CHECKING:' blocks (same denylist applies)."""
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    type_checking_imports: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        if not isinstance(node.test, ast.Name) or node.test.id != "TYPE_CHECKING":
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Import):
                for alias in child.names:
                    type_checking_imports.add(alias.name)
                    type_checking_imports.add(alias.name.split(".")[0])
            elif isinstance(child, ast.ImportFrom) and child.module:
                type_checking_imports.add(child.module)
                type_checking_imports.add(child.module.split(".")[0])
    return type_checking_imports


def test_gating_does_not_import_forbidden_modules():
    """Gating must not import pathlib, importlib, sqlite, evidence_resolver, store_sqlite, CLI, or os."""
    path = _gating_source_path()
    assert path.exists(), f"gating.py not found at {path}"
    imported = _imported_modules_from_source(path)
    for disallowed in GATING_IMPORT_DENYLIST:
        for m in imported:
            if m == disallowed or m.startswith(disallowed + "."):
                pytest.fail(f"gating.py must not import {disallowed!r}; found {m!r} in {sorted(imported)}")
    type_checking_only = _type_checking_imports_from_source(path)
    for disallowed in GATING_IMPORT_DENYLIST:
        for m in type_checking_only:
            if m == disallowed or m.startswith(disallowed + "."):
                pytest.fail(
                    f"gating.py must not import {disallowed!r} inside TYPE_CHECKING; found {m!r} in {sorted(type_checking_only)}"
                )


def test_service_calls_resolve_evidence():
    """evaluate_and_record calls resolve_evidence when resolving bundle/evidence from store."""
    from crypto_analyzer.db.migrations import run_migrations
    from crypto_analyzer.db.migrations_phase3 import run_migrations_phase3
    from crypto_analyzer.promotion.gating import ThresholdConfig
    from crypto_analyzer.promotion.service import evaluate_and_record
    from crypto_analyzer.promotion.store_sqlite import create_candidate
    from crypto_analyzer.validation_bundle import ValidationBundle

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        run_migrations(conn, db_path)
        run_migrations_phase3(conn, db_path)
        cid = create_candidate(
            conn,
            dataset_id="ds1",
            run_id="run1",
            signal_name="sig_a",
            horizon=1,
            config_hash="x",
            git_commit="y",
        )
        # Evidence JSON with a bundle_path so service will call resolve_evidence
        evidence = {"bundle_path": "/nonexistent/bundle.json"}
        conn.execute(
            "UPDATE promotion_candidates SET evidence_json = ? WHERE candidate_id = ?",
            (json.dumps(evidence), cid),
        )
        conn.commit()

        with patch("crypto_analyzer.promotion.service.resolve_evidence") as resolve_mock:
            resolve_mock.return_value = (None, None, None, None)  # bundle load "fails"
            bundle = ValidationBundle(
                run_id="run1",
                dataset_id="ds1",
                signal_name="sig_a",
                freq="1h",
                horizons=[1],
                ic_summary_by_horizon={1: {"mean_ic": 0.03, "t_stat": 3.0, "n_obs": 200}},
                ic_decay_table=[],
                meta={},
            )
            _ = evaluate_and_record(
                conn,
                cid,
                ThresholdConfig(ic_mean_min=0.02, tstat_min=2.0),
                bundle,
                target_status="exploratory",
            )
            resolve_mock.assert_called_once()
            call_args = resolve_mock.call_args[0]
            assert call_args[0] == evidence  # evidence_json
        conn.close()
    finally:
        Path(db_path).unlink(missing_ok=True)
