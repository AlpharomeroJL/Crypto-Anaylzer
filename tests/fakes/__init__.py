"""Fake providers and fixtures for ingestion and provider tests (no live network)."""

from .providers import (
    FakeDexProvider,
    FakeDexProviderAlwaysFail,
    FakeDexProviderFailNThenSucceed,
    FakeSpotProvider,
    FakeSpotProviderAlwaysFail,
    FakeSpotProviderFailNThenSucceed,
)

__all__ = [
    "FakeDexProvider",
    "FakeDexProviderAlwaysFail",
    "FakeDexProviderFailNThenSucceed",
    "FakeSpotProvider",
    "FakeSpotProviderAlwaysFail",
    "FakeSpotProviderFailNThenSucceed",
]
