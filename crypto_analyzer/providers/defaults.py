"""
Default provider registry configuration.

Registers built-in providers and builds chains from config.yaml settings.
To add a new provider, register it here and add it to the priority list.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .cex.coinbase import CoinbaseSpotProvider
from .cex.kraken import KrakenSpotProvider
from .chain import DexSnapshotChain, SpotPriceChain
from .dex.dexscreener import DexscreenerDexProvider
from .registry import ProviderRegistry
from .resilience import RetryConfig

logger = logging.getLogger(__name__)

# Default provider priority (config.yaml can override these)
DEFAULT_SPOT_PRIORITY = ["coinbase", "kraken"]
DEFAULT_DEX_PRIORITY = ["dexscreener"]


def create_default_registry() -> ProviderRegistry:
    """Create a registry with all built-in providers."""
    registry = ProviderRegistry()
    registry.register_spot("coinbase", CoinbaseSpotProvider)
    registry.register_spot("kraken", KrakenSpotProvider)
    registry.register_dex("dexscreener", DexscreenerDexProvider)
    return registry


def load_provider_config() -> Dict[str, List[str]]:
    """
    Load provider priority lists from config.yaml.

    Expected YAML structure:
        providers:
          spot_priority: ["coinbase", "kraken"]
          dex_priority: ["dexscreener"]
    """
    try:
        from crypto_analyzer.config import get_config
        cfg = get_config()
        providers = cfg.get("providers", {})
        return {
            "spot_priority": providers.get("spot_priority", DEFAULT_SPOT_PRIORITY),
            "dex_priority": providers.get("dex_priority", DEFAULT_DEX_PRIORITY),
        }
    except Exception:
        return {
            "spot_priority": DEFAULT_SPOT_PRIORITY,
            "dex_priority": DEFAULT_DEX_PRIORITY,
        }


def create_spot_chain(
    registry: Optional[ProviderRegistry] = None,
    priority: Optional[List[str]] = None,
) -> SpotPriceChain:
    """Build a spot price chain with resilience wrappers."""
    reg = registry or create_default_registry()
    cfg = load_provider_config()
    order = priority or cfg["spot_priority"]
    providers = reg.build_spot_chain(order)
    return SpotPriceChain(
        providers=providers,
        retry_config=RetryConfig(max_retries=3, base_delay_s=0.5),
        lkg_max_age_seconds=300.0,
    )


def create_dex_chain(
    registry: Optional[ProviderRegistry] = None,
    priority: Optional[List[str]] = None,
) -> DexSnapshotChain:
    """Build a DEX snapshot chain with resilience wrappers."""
    reg = registry or create_default_registry()
    cfg = load_provider_config()
    order = priority or cfg["dex_priority"]
    providers = reg.build_dex_chain(order)
    return DexSnapshotChain(
        providers=providers,
        retry_config=RetryConfig(max_retries=3, base_delay_s=0.5),
        lkg_max_age_seconds=300.0,
    )
