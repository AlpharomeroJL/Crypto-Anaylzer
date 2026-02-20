"""RC null cache: key, load, save, manifest."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from crypto_analyzer.stats.rc_cache import (
    get_rc_cache_key,
    load_cached_null_max,
    load_manifest,
    save_cached_null_max,
)


def test_rc_cache_key_stable():
    k1 = get_rc_cache_key("fam1", "ds1", "abc", "mean_ic", 1, 200, 42, "stationary", 12)
    k2 = get_rc_cache_key("fam1", "ds1", "abc", "mean_ic", 1, 200, 42, "stationary", 12)
    assert k1 == k2
    k3 = get_rc_cache_key("fam1", "ds1", "abc", "mean_ic", 1, 201, 42, "stationary", 12)
    assert k3 != k1


def test_save_and_load_null_max():
    with tempfile.TemporaryDirectory() as tmp:
        cache_dir = Path(tmp)
        key = "testkey24"
        arr = np.array([0.1, 0.2, 0.15])
        save_cached_null_max(cache_dir, key, arr)
        loaded = load_cached_null_max(cache_dir, key)
        assert loaded is not None
        np.testing.assert_array_almost_equal(loaded, arr)
        manifest = load_manifest(cache_dir)
        assert key in manifest
        assert "sha256" in manifest[key]


def test_load_missing_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        assert load_cached_null_max(tmp, "nonexistent") is None
