"""Version and CHANGELOG consistency: __version__ matches latest CHANGELOG release."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_version_matches_changelog():
    """tools/check_version_changelog.py exits 0 when __version__ matches latest CHANGELOG."""
    root = Path(__file__).resolve().parent.parent
    r = subprocess.run(
        [sys.executable, "tools/check_version_changelog.py"],
        capture_output=True,
        text=True,
        cwd=str(root),
        timeout=10,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
