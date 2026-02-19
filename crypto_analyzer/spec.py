"""
Research spec versioning and research-only boundary checks.
"""

from __future__ import annotations

from pathlib import Path

RESEARCH_SPEC_VERSION = "5.0"

# Forbidden substrings in source (research-only guardrail; fail CI if present).
# Expands to: order, submit, broker, exchange account, api key, secret, withdraw, etc.
_FORBIDDEN_KEYWORDS = [
    "api_key",
    "api_secret",
    "secret_key",
    "private_key",
    "order.execute",
    "place_order",
    "submit_order",
    "submit_order(",
    "broker.",
    "exchange.execute",
    "sign_transaction",
    "wallet.sign",
    "withdraw",
    "withdrawal",
    "transfer_funds",
    "exchange account",
    "account.balance",
]
# Only scan these directories (avoids false positives from docs, diagrams, reports, venv, .svg/.png/.json).
_SCAN_DIRS = ("crypto_analyzer", "cli", "tools")


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
    scan_dirs: tuple[str, ...] = _SCAN_DIRS,
) -> None:
    """
    Scan Python source under crypto_analyzer/, cli/, tools/ for forbidden keywords.
    Raise RuntimeError if any found. Does not scan docs/, reports/, .venv/, or non-.py files.
    """
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent
    if not root.is_dir():
        return

    found: list[str] = []
    for dir_name in scan_dirs:
        dir_path = root / dir_name
        if not dir_path.is_dir():
            continue
        for path in dir_path.rglob("*.py"):
            if path.name == "spec.py":
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
