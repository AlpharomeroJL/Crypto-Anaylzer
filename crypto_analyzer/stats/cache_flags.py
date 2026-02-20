"""
Single source of truth for cache disable: env + caller flag.
Phase 3 PR3. Used by factor_cache, regime_cache, reportv2, RC cache.
"""

from __future__ import annotations

import os


def is_cache_disabled(no_cache_flag: bool = False) -> bool:
    """
    True if caching should be skipped (do not use cache, do not write cache).
    - Env CRYPTO_ANALYZER_NO_CACHE=1 -> disabled.
    - no_cache_flag True (e.g. CLI --no-cache or force) -> disabled.
    """
    if no_cache_flag:
        return True
    return os.environ.get("CRYPTO_ANALYZER_NO_CACHE", "").strip() == "1"
