"""Hypothesis ID: order-invariant payload -> same hypothesis_id. Phase 3 sweep registry."""

from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.sweeps.hypothesis_id import compute_hypothesis_id


def test_hypothesis_id_deterministic():
    """Same payload -> same hypothesis_id."""
    payload = {
        "signal_name": "momentum_24h",
        "horizon": 1,
        "estimator": "rolling_ols",
        "params": {"window": 24},
        "regime_run_id": "",
    }
    id1 = compute_hypothesis_id(payload)
    id2 = compute_hypothesis_id(payload)
    assert id1 == id2
    assert id1.startswith("hyp_")
    assert len(id1) == 20


def test_hypothesis_id_key_order_invariant():
    """Different key order in dict -> same hypothesis_id."""
    p1 = {"signal_name": "s", "horizon": 4, "regime_run_id": ""}
    p2 = {"horizon": 4, "regime_run_id": "", "signal_name": "s"}
    assert compute_hypothesis_id(p1) == compute_hypothesis_id(p2)


def test_hypothesis_id_different_payload_different_id():
    """Different payload -> different hypothesis_id."""
    p1 = {"signal_name": "a", "horizon": 1}
    p2 = {"signal_name": "a", "horizon": 4}
    assert compute_hypothesis_id(p1) != compute_hypothesis_id(p2)


def test_hypothesis_id_params_order_invariant():
    """Params dict key order should not change hypothesis_id (canonicalized)."""
    p1 = {"signal_name": "s", "horizon": 1, "params": {"b": 2, "a": 1}}
    p2 = {"signal_name": "s", "horizon": 1, "params": {"a": 1, "b": 2}}
    assert compute_hypothesis_id(p1) == compute_hypothesis_id(p2)


def test_hypothesis_id_minimal_payload():
    """Minimal payload (signal_name, horizon only) still produces valid id."""
    payload = {"signal_name": "x", "horizon": 12}
    hid = compute_hypothesis_id(payload)
    assert hid.startswith("hyp_") and len(hid) == 20
