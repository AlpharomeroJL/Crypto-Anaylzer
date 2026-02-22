"""
Plugin interfaces and registry. Phase 3 A2.
Transforms and stats procedures; versioned contracts; explicit registration.
"""

from __future__ import annotations

from .api import (
    PLUGIN_API_VERSION,
    STAT_PROCEDURE_PLUGIN_VERSION,
    TRANSFORM_PLUGIN_VERSION,
    StatProcedurePlugin,
    TransformPlugin,
    get_plugin_registry,
    register_stat_procedure,
    register_transform_plugin,
)

__all__ = [
    "PLUGIN_API_VERSION",
    "STAT_PROCEDURE_PLUGIN_VERSION",
    "TRANSFORM_PLUGIN_VERSION",
    "StatProcedurePlugin",
    "TransformPlugin",
    "get_plugin_registry",
    "register_stat_procedure",
    "register_transform_plugin",
]
