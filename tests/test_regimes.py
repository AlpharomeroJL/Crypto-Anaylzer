"""Regime classification and explanation."""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.regimes import classify_market_regime, explain_regime


def test_classify_market_regime():
    assert classify_market_regime(-1.5, "stable", "stable") == "macro_beta"
    assert classify_market_regime(1.5, "stable", "stable") == "dispersion"
    assert classify_market_regime(0.5, "stable", "stable") == "chop"
    assert classify_market_regime(-1.0, "rising", "compressed") == "risk_off"


def test_explain_regime():
    assert len(explain_regime("macro_beta")) > 0
    assert len(explain_regime("dispersion")) > 0
