"""
Import app and doctor without running Streamlit to catch shadowing / UnboundLocalError.
No Streamlit runtime is started.
"""

from __future__ import annotations

import pytest


def test_import_doctor_without_runtime():
    """Import crypto_analyzer.doctor without executing main (no DB/venv required for import)."""
    import crypto_analyzer.doctor as doctor  # noqa: F401

    assert hasattr(doctor, "check_env")
    assert hasattr(doctor, "main")


def test_import_app_without_streamlit_run():
    """Import app module without starting Streamlit (ensures no inline import shadowing). Skips if [ui] extra not installed."""
    pytest.importorskip("streamlit")
    import crypto_analyzer.cli.app as app

    assert hasattr(app, "main")
