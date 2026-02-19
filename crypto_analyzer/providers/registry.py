"""
Provider registry: central catalog of available providers.

Providers register themselves here. The registry is config-driven: a YAML
priority list determines which providers are tried in what order for each
provider type (spot, dex).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Type, Union

from .base import DexSnapshotProvider, SpotPriceProvider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """
    Singleton-style registry mapping provider names to classes/instances.

    Usage:
        registry = ProviderRegistry()
        registry.register_spot("coinbase", CoinbaseSpotProvider)
        registry.register_spot("kraken", KrakenSpotProvider)

        chain = registry.build_spot_chain(["coinbase", "kraken"])
    """

    def __init__(self) -> None:
        self._spot_factories: Dict[str, Any] = {}
        self._dex_factories: Dict[str, Any] = {}
        self._spot_instances: Dict[str, SpotPriceProvider] = {}
        self._dex_instances: Dict[str, DexSnapshotProvider] = {}

    def register_spot(
        self,
        name: str,
        factory: Union[Type[SpotPriceProvider], SpotPriceProvider],
    ) -> None:
        """Register a spot price provider by name."""
        self._spot_factories[name] = factory
        logger.debug("Registered spot provider: %s", name)

    def register_dex(
        self,
        name: str,
        factory: Union[Type[DexSnapshotProvider], DexSnapshotProvider],
    ) -> None:
        """Register a DEX snapshot provider by name."""
        self._dex_factories[name] = factory
        logger.debug("Registered DEX provider: %s", name)

    def get_spot(self, name: str) -> SpotPriceProvider:
        """Get or instantiate a spot provider by name."""
        if name not in self._spot_instances:
            factory = self._spot_factories.get(name)
            if factory is None:
                raise KeyError(
                    f"Unknown spot provider '{name}'. "
                    f"Available: {list(self._spot_factories)}"
                )
            if isinstance(factory, type):
                self._spot_instances[name] = factory()
            else:
                self._spot_instances[name] = factory
        return self._spot_instances[name]

    def get_dex(self, name: str) -> DexSnapshotProvider:
        """Get or instantiate a DEX provider by name."""
        if name not in self._dex_instances:
            factory = self._dex_factories.get(name)
            if factory is None:
                raise KeyError(
                    f"Unknown DEX provider '{name}'. "
                    f"Available: {list(self._dex_factories)}"
                )
            if isinstance(factory, type):
                self._dex_instances[name] = factory()
            else:
                self._dex_instances[name] = factory
        return self._dex_instances[name]

    @property
    def spot_names(self) -> List[str]:
        return list(self._spot_factories)

    @property
    def dex_names(self) -> List[str]:
        return list(self._dex_factories)

    def build_spot_chain(
        self, priority: Optional[List[str]] = None
    ) -> List[SpotPriceProvider]:
        """Build an ordered list of spot providers from a priority list."""
        names = priority or list(self._spot_factories)
        return [self.get_spot(n) for n in names if n in self._spot_factories]

    def build_dex_chain(
        self, priority: Optional[List[str]] = None
    ) -> List[DexSnapshotProvider]:
        """Build an ordered list of DEX providers from a priority list."""
        names = priority or list(self._dex_factories)
        return [self.get_dex(n) for n in names if n in self._dex_factories]
