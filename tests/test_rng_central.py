"""
Central RNG: salt separation and cross-process reproducibility.
"""

import subprocess
import sys
from pathlib import Path

import numpy as np

# Import from central module
from crypto_analyzer.rng import SALT_RC_NULL, SEED_ROOT_VERSION, rng_for, seed_root


def test_rng_salt_separation():
    """Same run_key, different salts => different sequences."""
    run_key = "test_run_key_1"
    r1 = rng_for(run_key, "stationary_bootstrap")
    r2 = rng_for(run_key, SALT_RC_NULL)
    u1 = r1.random(10)
    u2 = r2.random(10)
    assert not np.allclose(u1, u2), "Different salts must yield different sequences"


def test_rng_same_salt_same_sequence():
    """Same run_key and salt => same sequence."""
    run_key = "test_run_key_2"
    r1 = rng_for(run_key, "cscv_splits")
    r2 = rng_for(run_key, "cscv_splits")
    u1 = r1.random(20)
    u2 = r2.random(20)
    np.testing.assert_array_almost_equal(u1, u2)


def test_seed_root_version_constant():
    """SEED_ROOT_VERSION is the contract; default seed_root uses it."""
    assert SEED_ROOT_VERSION == 1
    s_default = seed_root("rk", salt="x")
    s_explicit = seed_root("rk", salt="x", version=SEED_ROOT_VERSION)
    assert s_default == s_explicit


def test_seed_root_stable():
    """seed_root is deterministic and in valid range."""
    s = seed_root("rk", salt="x", version=SEED_ROOT_VERSION)
    assert s == seed_root("rk", salt="x", version=1)
    assert 0 <= s < 2**63
    assert seed_root("rk", salt="y", version=1) != s


def test_seed_root_fold_id_normalized_int_and_str_same():
    """fold_id int vs str same value yields same seed (normalized before hashing)."""
    s_int = seed_root("rk", salt="s", fold_id=42)
    s_str = seed_root("rk", salt="s", fold_id="42")
    assert s_int == s_str


def test_seed_root_fold_id_prefix_avoids_collision():
    """fold_id is prefixed with 'fold:' so it does not collide with raw hypothesis_id in salt."""
    s_fold = seed_root("rk", salt="s", fold_id="h1|1")
    s_raw = seed_root("rk", salt="s|h1|1", fold_id=None)
    assert s_fold != s_raw


def test_rng_reproducible_across_process():
    """Spawn subprocess twice with same run_key+salt => same first N draws."""
    root = Path(__file__).resolve().parent.parent
    code = f"""
import sys
sys.path.insert(0, {repr(str(root))})
from crypto_analyzer.rng import SALT_RC_NULL, rng_for
r = rng_for('cross_process_rk', SALT_RC_NULL)
vals = r.random(5).tolist()
print(','.join(map(str, vals)))
"""
    out1 = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(root),
    )
    out2 = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(root),
    )
    assert out1.returncode == 0, out1.stderr or out1.stdout
    assert out2.returncode == 0, out2.stderr or out2.stdout
    assert out1.stdout.strip() == out2.stdout.strip(), "Same run_key+salt must yield same draws across processes"
    # Parse and check numeric
    vals = [float(x) for x in out1.stdout.strip().split(",")]
    assert len(vals) == 5
    assert all(0 <= v <= 1 for v in vals)
