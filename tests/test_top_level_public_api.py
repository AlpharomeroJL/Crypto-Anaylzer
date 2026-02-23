"""
Tests for the top-level public API (crypto_analyzer/__init__.py).
Ensures __version__, __all__, and facade re-exports are present and that importing does not pull cli.
"""

from __future__ import annotations

import sys

# Expected top-level __all__ (must match crypto_analyzer/__init__.py exactly).
EXPECTED_TOP_LEVEL_ALL = {
    "__version__",
    "artifacts",
    "core",
    "data",
    "governance",
    "pipeline",
    "rng",
    "stats",
}


def test_import_crypto_analyzer_works():
    """import crypto_analyzer as ca works."""
    import crypto_analyzer as ca

    assert ca is not None


def test_top_level_has_version():
    """crypto_analyzer exposes __version__ as non-empty string equal to 0.3.0."""
    import crypto_analyzer as ca

    assert hasattr(ca, "__version__")
    assert isinstance(ca.__version__, str)
    assert len(ca.__version__.strip()) > 0
    assert ca.__version__ == "0.3.0"


def test_top_level_has_explicit_all():
    """crypto_analyzer has __all__ and it matches the expected set exactly."""
    import crypto_analyzer as ca

    assert hasattr(ca, "__all__")
    assert set(ca.__all__) == EXPECTED_TOP_LEVEL_ALL


def test_top_level_each_all_name_exported():
    """For each name in __all__, crypto_analyzer has that attribute."""
    import crypto_analyzer as ca

    for name in ca.__all__:
        assert hasattr(ca, name), f"crypto_analyzer must export {name!r} (in __all__)"


def test_rng_exported_at_top_level():
    """rng is re-exported at top-level as namespace only (shim to core.seeding)."""
    import crypto_analyzer as ca

    assert hasattr(ca, "rng")
    assert "rng" in ca.__all__


def test_importing_crypto_analyzer_does_not_pull_cli():
    """Importing crypto_analyzer does not add crypto_analyzer.cli to sys.modules."""
    before = set(sys.modules.keys())
    import crypto_analyzer  # noqa: F401

    after = set(sys.modules.keys())
    new_modules = after - before
    assert "crypto_analyzer.cli" not in new_modules, "Top-level import must not pull in crypto_analyzer.cli"


def test_version_shim_equals_canonical():
    """crypto_analyzer.version is a shim: __version__ equals _version.__version__ and is 0.3.0."""
    from crypto_analyzer._version import __version__ as v1
    from crypto_analyzer.version import __version__ as v2

    assert v1 == v2 == "0.3.0"
