"""
Assert __version__ matches the latest release in CHANGELOG.md.
Run from repo root: python tools/check_version_changelog.py [--expected-version X.Y.Z]
With --expected-version, also requires that tag/expected matches __version__ and CHANGELOG.
Exits 0 if match, 1 otherwise. Used in CI and release checklist.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _latest_changelog_version() -> str | None:
    path = _repo_root() / "CHANGELOG.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    # First ## [X.Y.Z] or ## [vX.Y.Z] is the latest release
    m = re.search(r"^##\s*\[v?(\d+\.\d+\.\d+)\]", text, re.MULTILINE)
    return m.group(1) if m else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Check __version__ vs CHANGELOG (and optional tag version).")
    ap.add_argument(
        "--expected-version",
        metavar="X.Y.Z",
        help="Required version (e.g. from tag); fails if __version__ or CHANGELOG differs.",
    )
    args = ap.parse_args()
    try:
        from crypto_analyzer._version import __version__
    except Exception as e:
        print(f"Could not read __version__: {e}", file=sys.stderr)
        return 1
    latest = _latest_changelog_version()
    if not latest:
        print("CHANGELOG.md has no ## [X.Y.Z] release header.", file=sys.stderr)
        return 1
    expected = args.expected_version
    if expected:
        if __version__ != expected:
            print(
                f"Version mismatch: crypto_analyzer.__version__={__version__!r} vs expected (tag) {expected!r}",
                file=sys.stderr,
            )
            return 1
        if latest != expected:
            print(
                f"CHANGELOG.md latest={latest!r} vs expected (tag) {expected!r}",
                file=sys.stderr,
            )
            return 1
        return 0
    if __version__ != latest:
        print(
            f"Version mismatch: crypto_analyzer.__version__={__version__!r} vs CHANGELOG.md latest={latest!r}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
