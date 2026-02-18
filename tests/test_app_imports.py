"""
Import app and doctor without running Streamlit to catch shadowing / UnboundLocalError.
No Streamlit runtime is started.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Repo root on path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_import_doctor_without_runtime():
    """Import crypto_analyzer.doctor without executing main (no DB/venv required for import)."""
    import crypto_analyzer.doctor as doctor  # noqa: F401
    assert hasattr(doctor, "check_env")
    assert hasattr(doctor, "main")


def test_import_app_without_streamlit_run():
    """Import app module without starting Streamlit (ensures no inline import shadowing)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("app", ROOT / "cli" / "app.py")
    assert spec is not None and spec.loader is not None
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    assert hasattr(app, "main")
