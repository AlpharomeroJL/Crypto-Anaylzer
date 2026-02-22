"""Phase 3 A2: Plugin registry and versioned contracts."""

from __future__ import annotations

from crypto_analyzer.plugins import (
    PLUGIN_API_VERSION,
    STAT_PROCEDURE_PLUGIN_VERSION,
    TRANSFORM_PLUGIN_VERSION,
    get_plugin_registry,
    register_stat_procedure,
    register_transform_plugin,
)
from crypto_analyzer.plugins.api import StatProcedurePlugin, TransformPlugin


def test_plugin_api_versions_defined():
    assert PLUGIN_API_VERSION == 1
    assert TRANSFORM_PLUGIN_VERSION == 1
    assert STAT_PROCEDURE_PLUGIN_VERSION == 1


def test_register_and_get_transform_plugin():
    def _build():
        class T:
            def transform(self, df):
                return df

        return T()

    p = TransformPlugin(
        name="noop_exogenous",
        version=1,
        kind="exogenous",
        schema_version=TRANSFORM_PLUGIN_VERSION,
        params_schema={},
        build=_build,
    )
    register_transform_plugin(p)
    reg = get_plugin_registry()
    assert "noop_exogenous" in reg["transform_plugins"]
    assert reg["transform_plugins"]["noop_exogenous"]["version"] == 1
    assert reg["transform_plugins"]["noop_exogenous"]["kind"] == "exogenous"


def test_register_and_get_stat_procedure_plugin():
    def _run(bundle, context):
        return {"results": {}, "artifacts": {}}

    p = StatProcedurePlugin(name="dummy_stat", version=1, schema_version=STAT_PROCEDURE_PLUGIN_VERSION, run=_run)
    register_stat_procedure(p)
    reg = get_plugin_registry()
    assert "dummy_stat" in reg["stat_plugins"]
    assert reg["stat_plugins"]["dummy_stat"]["version"] == 1
