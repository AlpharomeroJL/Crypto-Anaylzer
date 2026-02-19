"""
Research spec versioning and research-only boundary checks.
"""

from __future__ import annotations

from pathlib import Path

RESEARCH_SPEC_VERSION = "5.0"

# Forbidden substrings in source (conservative; exclude docs/comments that say "research-only" etc.)
_FORBIDDEN_KEYWORDS = [
    "api_key",
    "api_secret",
    "secret_key",
    "private_key",
    "order.execute",
    "place_order",
    "submit_order",
    "broker.",
    "exchange.execute",
    "sign_transaction",
    "wallet.sign",
]
# Allow these in comments/docs (we scan file content; if line is comment/doc we could skip - for simplicity we exclude known doc paths)
_EXCLUDED_PATHS = (
    "README",
    "INSTITUTIONAL",
    "CONTRIBUTING",
    "DEPLOY",
    "HANDOFF",
    "WINDOWS_24_7",
    "docs/",
    ".md",
    "CHANGELOG",
    "tests/",
)


def spec_summary() -> dict:
    """Return version and key module versions if present."""
    out = {"research_spec_version": RESEARCH_SPEC_VERSION}
    try:
        import crypto_analyzer  # noqa: F401

        out["package"] = "crypto_analyzer"
    except Exception:
        pass
    return out


def validate_research_only_boundary(
    repo_root: str | Path | None = None,
    scan_extensions: tuple = (".py",),
    exclude_dirs: tuple = (".git", "__pycache__", ".venv", "venv", "node_modules"),
) -> None:
    """
    Scan repo text for forbidden keywords. Raise RuntimeError if any found.
    Excludes paths containing _EXCLUDED_PATHS (docs, README, etc.).
    """
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent
    if not root.is_dir():
        return

    found: list[str] = []
    for ext in scan_extensions:
        for path in root.rglob(f"*{ext}"):
            if any(ex in path.as_posix() for ex in exclude_dirs):
                continue
            if any(ex in path.as_posix() for ex in _EXCLUDED_PATHS):
                continue
            if "spec.py" in path.name:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
                lower = text.lower()
                for kw in _FORBIDDEN_KEYWORDS:
                    if kw in lower:
                        found.append(f"{path.relative_to(root)}: forbidden '{kw}'")
            except Exception:
                continue

    if found:
        raise RuntimeError("Research-only boundary violation: " + "; ".join(found[:10]))
