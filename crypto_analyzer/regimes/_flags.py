"""Feature flag for Phase 3 regimes. Read at call time so modules stay importable when OFF."""

from __future__ import annotations

import os


def is_regimes_enabled() -> bool:
    """True iff CRYPTO_ANALYZER_ENABLE_REGIMES is set to 1, true, or yes."""
    v = os.environ.get("CRYPTO_ANALYZER_ENABLE_REGIMES", "0").strip().lower()
    return v in ("1", "true", "yes")
