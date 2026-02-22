"""Phase 3 A2: Stat procedure plugin must return deterministic outputs when seeded."""

from __future__ import annotations

from crypto_analyzer.plugins import register_stat_procedure
from crypto_analyzer.plugins.api import StatProcedurePlugin


def test_stat_procedure_with_seed_in_context_is_deterministic():
    """When context contains seed/run_key, same inputs yield same outputs."""

    def _run(bundle, context):
        seed = context.get("seed", 42)
        run_key = context.get("run_key", "")
        return {"results": {"seed": seed, "run_key_hash": hash(run_key) % (2**31)}, "artifacts": {}}

    p = StatProcedurePlugin(name="determinism_test_plugin", version=1, run=_run)
    register_stat_procedure(p)
    ctx = {"seed": 12345, "run_key": "rk_abc"}
    out1 = p.run({}, ctx)
    out2 = p.run({}, ctx)
    assert out1 == out2
    assert out1["results"]["seed"] == 12345
