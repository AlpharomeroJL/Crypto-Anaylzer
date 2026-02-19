"""
Provider architecture for cryptocurrency data ingestion.

Extensible plugin system for CEX spot price feeds and DEX snapshot sources.
Providers are registered via a config-driven priority chain with automatic
fallback, circuit breakers, retry/backoff, and last-known-good behavior.
"""

from __future__ import annotations

from .base import (
    DexSnapshot,
    DexSnapshotProvider,
    ProviderHealth,
    ProviderStatus,
    SpotPriceProvider,
    SpotQuote,
)
from .chain import DexSnapshotChain, SpotPriceChain
from .registry import ProviderRegistry
from .resilience import CircuitBreaker, RetryConfig, resilient_call

__all__ = [
    "SpotQuote",
    "DexSnapshot",
    "SpotPriceProvider",
    "DexSnapshotProvider",
    "ProviderHealth",
    "ProviderStatus",
    "ProviderRegistry",
    "SpotPriceChain",
    "DexSnapshotChain",
    "CircuitBreaker",
    "RetryConfig",
    "resilient_call",
]
