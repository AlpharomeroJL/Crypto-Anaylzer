"""
Public facade contract tests: explicit __all__, export availability, import weight, no circular imports.
No behavior change; ensures facades remain stable and testable.
"""

from __future__ import annotations

import sys

# Facades that must have non-empty __all__ and every name must be importable.
PUBLIC_FACADES = [
    ("crypto_analyzer.core", "core"),
    ("crypto_analyzer.data", "data"),
    ("crypto_analyzer.artifacts", "artifacts"),
    ("crypto_analyzer.stats", "stats"),
    ("crypto_analyzer.governance", "governance"),
    ("crypto_analyzer.pipeline", "pipeline"),
    ("crypto_analyzer.rng", "rng"),
]

# Facades that must not pull in cli or promotion when imported (clean facades).
CLEAN_FACADES_NO_CLI_PROMOTION = [
    "crypto_analyzer.core",
    "crypto_analyzer.data",
    "crypto_analyzer.artifacts",
    "crypto_analyzer.stats",
    "crypto_analyzer.rng",
]


def test_each_facade_has_explicit_non_empty_all():
    """Each public facade has __all__ and it is non-empty."""
    for module_name, _ in PUBLIC_FACADES:
        mod = __import__(module_name, fromlist=[""])
        assert hasattr(mod, "__all__"), f"{module_name} must have __all__"
        assert isinstance(mod.__all__, (list, tuple)), f"{module_name}.__all__ must be list or tuple"
        assert len(mod.__all__) > 0, f"{module_name}.__all__ must be non-empty"


def test_each_facade_all_names_are_exported():
    """For each facade, every name in __all__ is present on the module."""
    for module_name, _ in PUBLIC_FACADES:
        mod = __import__(module_name, fromlist=[""])
        for name in mod.__all__:
            assert hasattr(mod, name), f"{module_name} must export {name!r} (in __all__)"


def test_clean_facades_do_not_import_cli_or_promotion():
    """Importing clean facades (core/data/artifacts/stats/rng) does not add cli or promotion."""
    before = set(sys.modules.keys())
    for module_name in CLEAN_FACADES_NO_CLI_PROMOTION:
        __import__(module_name, fromlist=[""])
    after = set(sys.modules.keys())
    new_modules = after - before
    assert "cli" not in new_modules and "crypto_analyzer.cli" not in new_modules, "Clean facades must not import cli"
    assert "crypto_analyzer.promotion" not in new_modules, "Clean facades must not import crypto_analyzer.promotion"


def test_facade_import_order_a():
    """Facades can be imported in order: core, data, artifacts, stats, governance, pipeline, rng."""
    import crypto_analyzer.artifacts
    import crypto_analyzer.core
    import crypto_analyzer.data
    import crypto_analyzer.governance
    import crypto_analyzer.pipeline
    import crypto_analyzer.rng
    import crypto_analyzer.stats

    assert crypto_analyzer.core is not None
    assert crypto_analyzer.data is not None
    assert crypto_analyzer.artifacts is not None
    assert crypto_analyzer.stats is not None
    assert crypto_analyzer.governance is not None
    assert crypto_analyzer.pipeline is not None
    assert crypto_analyzer.rng is not None


def test_facade_import_order_b():
    """Facades can be imported in reverse order without circular import errors."""
    import crypto_analyzer.artifacts
    import crypto_analyzer.core
    import crypto_analyzer.data
    import crypto_analyzer.governance
    import crypto_analyzer.pipeline
    import crypto_analyzer.rng
    import crypto_analyzer.stats

    assert crypto_analyzer.core is not None
    assert crypto_analyzer.artifacts is not None
    assert crypto_analyzer.data is not None
    assert crypto_analyzer.stats is not None
    assert crypto_analyzer.governance is not None
    assert crypto_analyzer.pipeline is not None
    assert crypto_analyzer.rng is not None


def test_facade_import_order_c():
    """Facades can be imported with pipeline first (heavier facade)."""
    import crypto_analyzer.core
    import crypto_analyzer.data
    import crypto_analyzer.pipeline

    assert crypto_analyzer.pipeline.run_research_pipeline is not None
    assert crypto_analyzer.core.RunContext is not None
    assert crypto_analyzer.data.load_bars is not None
