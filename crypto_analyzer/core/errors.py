"""
Shared exception types for crypto_analyzer.
Stable surface; extend only. No behavior change.
"""

from __future__ import annotations


class CryptoAnalyzerError(Exception):
    """Base exception for crypto_analyzer; catch this for any package-raised error."""

    pass


__all__ = ["CryptoAnalyzerError"]
