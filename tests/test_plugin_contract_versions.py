"""Phase 3 A2: Plugin contract versions are fixed and used in meta/lineage."""

from __future__ import annotations

from crypto_analyzer.plugins import (
    PLUGIN_API_VERSION,
    STAT_PROCEDURE_PLUGIN_VERSION,
    TRANSFORM_PLUGIN_VERSION,
    get_plugin_registry,
)


def test_plugin_registry_snapshot_includes_schema_versions():
    reg = get_plugin_registry()
    assert "transform_plugins" in reg
    assert "stat_plugins" in reg
    for name, meta in reg["transform_plugins"].items():
        assert meta["schema_version"] == TRANSFORM_PLUGIN_VERSION
    for name, meta in reg["stat_plugins"].items():
        assert meta["schema_version"] == STAT_PROCEDURE_PLUGIN_VERSION


def test_plugin_api_version_constant():
    assert isinstance(PLUGIN_API_VERSION, int)
    assert PLUGIN_API_VERSION >= 1
