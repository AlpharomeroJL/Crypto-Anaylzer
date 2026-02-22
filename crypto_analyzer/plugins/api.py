"""
Plugin API: versioned contracts for transforms and stat procedures.
Phase 3 A2. Explicit registration; no dynamic filesystem imports by default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# Contract versions for artifact meta and lineage
PLUGIN_API_VERSION = 1
TRANSFORM_PLUGIN_VERSION = 1
STAT_PROCEDURE_PLUGIN_VERSION = 1


@dataclass
class TransformPlugin:
    """
    Transform plugin: builds TrainableTransform or ExogenousTransform.
    Required: name, version, kind, schema_version, params_schema; build(...) returns implementation.
    """

    name: str
    version: int
    kind: str  # "exogenous" | "trainable"
    schema_version: int = TRANSFORM_PLUGIN_VERSION
    params_schema: Dict[str, Any] = field(default_factory=dict)
    build: Optional[Callable[..., Any]] = None  # (params?) -> TrainableTransform | ExogenousTransform

    def __post_init__(self) -> None:
        if self.build is None:
            raise ValueError("TransformPlugin.build must be set")


@dataclass
class StatProcedurePlugin:
    """
    Stat procedure plugin: run(bundle, context) -> results + artifacts.
    Must return deterministic outputs when seeded (context carries seed/run_key).
    """

    name: str
    version: int
    schema_version: int = STAT_PROCEDURE_PLUGIN_VERSION
    run: Optional[Callable[..., Dict[str, Any]]] = None  # (bundle, context) -> {results, artifacts}

    def __post_init__(self) -> None:
        if self.run is None:
            raise ValueError("StatProcedurePlugin.run must be set")


# Registry: explicit registration only
_TransformRegistry: Dict[str, TransformPlugin] = {}
_StatProcedureRegistry: Dict[str, StatProcedurePlugin] = {}


def register_transform_plugin(plugin: TransformPlugin) -> None:
    """Register a transform plugin by name. Overwrites if same name."""
    _TransformRegistry[plugin.name] = plugin


def register_stat_procedure(plugin: StatProcedurePlugin) -> None:
    """Register a stat procedure plugin by name. Overwrites if same name."""
    _StatProcedureRegistry[plugin.name] = plugin


def get_plugin_registry() -> Dict[str, Any]:
    """Return snapshot of registered plugins (for meta/lineage). Keys: transform_plugins, stat_plugins."""
    return {
        "transform_plugins": {
            name: {
                "name": p.name,
                "version": p.version,
                "kind": p.kind,
                "schema_version": p.schema_version,
            }
            for name, p in _TransformRegistry.items()
        },
        "stat_plugins": {
            name: {
                "name": p.name,
                "version": p.version,
                "schema_version": p.schema_version,
            }
            for name, p in _StatProcedureRegistry.items()
        },
    }


def get_transform_plugin(name: str) -> Optional[TransformPlugin]:
    """Return transform plugin by name or None."""
    return _TransformRegistry.get(name)


def get_stat_procedure_plugin(name: str) -> Optional[StatProcedurePlugin]:
    """Return stat procedure plugin by name or None."""
    return _StatProcedureRegistry.get(name)


def list_transform_plugins() -> List[str]:
    """Return registered transform plugin names."""
    return list(_TransformRegistry.keys())


def list_stat_procedure_plugins() -> List[str]:
    """Return registered stat procedure plugin names."""
    return list(_StatProcedureRegistry.keys())
