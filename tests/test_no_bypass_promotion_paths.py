"""Phase 3 A3: No code path must bypass governance API for candidate/accepted status."""

from __future__ import annotations

import ast
from pathlib import Path


def _find_dangerous_calls(path: Path) -> list[tuple[int, str]]:
    """Find update_status(..., 'candidate'|'accepted') or direct promote_to_* from non-governance code."""
    dangerous = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                name = func.attr
                if name in ("promote_to_candidate", "promote_to_accepted"):
                    mod = None
                    if isinstance(func.value, ast.Name):
                        mod = func.value.id
                    elif isinstance(func.value, ast.Attribute):
                        mod = getattr(func.value, "attr", None) or getattr(func.value.value, "id", None)
                    if mod != "governance" and "promote" not in str(path):
                        dangerous.append((node.lineno, f"direct {name}"))
            elif isinstance(func, ast.Name) and func.id == "update_status":
                for kw in node.keywords:
                    if (
                        kw.arg == "status"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value in ("candidate", "accepted")
                    ):
                        dangerous.append((node.lineno, "update_status with candidate/accepted"))
                        break
    return dangerous


def test_no_direct_promote_to_candidate_accepted_outside_governance():
    """Only governance/promotion code may call promote_to_candidate or promote_to_accepted."""
    root = Path(__file__).resolve().parent.parent
    allowed_prefixes = (
        "crypto_analyzer/governance/",
        "crypto_analyzer/promotion/",
        "tests/",
    )
    for path in root.rglob("*.py"):
        rel = str(path.relative_to(root)).replace("\\", "/")
        if any(rel.startswith(p) for p in allowed_prefixes):
            continue
        for line, msg in _find_dangerous_calls(path):
            raise AssertionError(f"{rel} line {line}: {msg} must go through governance API only")
