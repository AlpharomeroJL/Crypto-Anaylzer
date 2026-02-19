"""
Single source for "now" time. Supports deterministic mode for tests via
CRYPTO_ANALYZER_DETERMINISTIC_TIME (ISO format, e.g. 2026-01-01T00:00:00Z).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone


def now_utc_iso() -> str:
    """
    Return current UTC time in ISO format (seconds).
    If env CRYPTO_ANALYZER_DETERMINISTIC_TIME is set, return that value instead.
    """
    fixed = os.environ.get("CRYPTO_ANALYZER_DETERMINISTIC_TIME", "").strip()
    if fixed:
        return fixed if fixed.endswith("Z") or "+" in fixed else f"{fixed}Z"
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
