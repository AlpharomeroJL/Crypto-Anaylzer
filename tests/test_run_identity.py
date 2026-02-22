"""
Phase 1 verification: run_key is deterministic and sensitive to semantic changes.
- Same config + same dataset (no timestamps/paths) -> run_key identical; run_instance_id can differ.
- Change factor param / engine_version / dataset_id_v2 -> run_key changes.
"""

from __future__ import annotations

from crypto_analyzer.governance import build_run_identity, compute_run_key


def test_run_key_identical_for_same_semantic_payload():
    """Same semantic payload (no timestamps/paths) -> same run_key."""
    payload = {
        "dataset_id_v2": "abc12",
        "config": {"signal": "sig_a", "horizon": 1, "factor": "momentum"},
        "engine_version": "v1",
        "config_version": "cfg1",
    }
    k1 = compute_run_key(payload)
    k2 = compute_run_key(payload)
    assert k1 == k2


def test_run_key_excludes_timestamps():
    """Different ts_utc / created_utc only -> run_key unchanged."""
    base = {
        "dataset_id_v2": "abc12",
        "config": {"signal": "sig_a", "horizon": 1},
        "engine_version": "v1",
        "config_version": "cfg1",
    }
    p1 = {**base, "ts_utc": "2026-01-01T00:00:00"}
    p2 = {**base, "ts_utc": "2026-02-01T12:00:00"}
    assert compute_run_key(p1) == compute_run_key(p2)


def test_run_instance_id_can_differ():
    """run_instance_id is passed in; same run_key, different instance ids."""
    semantic = {"dataset_id_v2": "d1", "config": {"signal": "s"}, "engine_version": "v1", "config_version": "c1"}
    ri1 = build_run_identity(semantic, "instance_001")
    ri2 = build_run_identity(semantic, "instance_002")
    assert ri1.run_key == ri2.run_key
    assert ri1.run_instance_id != ri2.run_instance_id


def test_run_key_changes_with_dataset_id_v2():
    """Change dataset_id_v2 -> run_key changes."""
    base = {"dataset_id_v2": "d1", "config": {"signal": "s"}, "engine_version": "v1", "config_version": "c1"}
    k1 = compute_run_key(base)
    base2 = {**base, "dataset_id_v2": "d2"}
    k2 = compute_run_key(base2)
    assert k1 != k2


def test_run_key_changes_with_engine_version():
    """Change engine_version -> run_key changes."""
    base = {"dataset_id_v2": "d1", "config": {"signal": "s"}, "engine_version": "v1", "config_version": "c1"}
    k1 = compute_run_key(base)
    base2 = {**base, "engine_version": "v2"}
    k2 = compute_run_key(base2)
    assert k1 != k2


def test_run_key_changes_with_factor_param():
    """Change a factor/config parameter -> run_key changes."""
    base = {"dataset_id_v2": "d1", "config": {"signal": "s", "horizon": 1}, "engine_version": "v1", "config_version": "c1"}
    k1 = compute_run_key(base)
    base2 = {"dataset_id_v2": "d1", "config": {"signal": "s", "horizon": 4}, "engine_version": "v1", "config_version": "c1"}
    k2 = compute_run_key(base2)
    assert k1 != k2
