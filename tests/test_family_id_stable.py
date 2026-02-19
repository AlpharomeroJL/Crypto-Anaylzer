"""Family ID: same payload (any key order) -> same family_id."""

from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.sweeps.family_id import compute_family_id


def test_family_id_deterministic():
    """Same payload -> same family_id."""
    payload = {"config_hash": "abc", "signals": ["a", "b"], "horizons": [1, 4], "regime_run_id": ""}
    id1 = compute_family_id(payload)
    id2 = compute_family_id(payload)
    assert id1 == id2
    assert id1.startswith("rcfam_")
    assert len(id1) == 22


def test_family_id_key_order_irrelevant():
    """Different key order in dict -> same family_id (canonicalized)."""
    p1 = {"config_hash": "x", "signals": ["s1"], "horizons": [1]}
    p2 = {"horizons": [1], "config_hash": "x", "signals": ["s1"]}
    assert compute_family_id(p1) == compute_family_id(p2)


def test_family_id_list_order_canonicalized():
    """List order is sorted for canonical form."""
    p1 = {"signals": ["b", "a"], "horizons": [4, 1]}
    p2 = {"signals": ["a", "b"], "horizons": [1, 4]}
    assert compute_family_id(p1) == compute_family_id(p2)


def test_family_id_different_payload_different_id():
    """Different payload -> different family_id."""
    p1 = {"signals": ["a"], "horizons": [1]}
    p2 = {"signals": ["a"], "horizons": [1, 4]}
    assert compute_family_id(p1) != compute_family_id(p2)
