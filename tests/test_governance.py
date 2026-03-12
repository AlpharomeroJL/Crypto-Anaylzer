"""Governance: manifest creation, save/load, file hashing."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from crypto_analyzer.artifacts import compute_file_sha256, snapshot_outputs
from crypto_analyzer.governance import (
    get_env_fingerprint,
    get_git_commit,
    load_manifests,
    make_run_manifest,
    save_manifest,
    stable_run_id,
)
from crypto_analyzer.timeutils import now_utc_iso


def test_get_git_commit_returns_string():
    s = get_git_commit()
    assert isinstance(s, str)
    assert len(s) <= 40 or s == "unknown"


def test_get_env_fingerprint_has_keys():
    d = get_env_fingerprint()
    assert "python_version" in d
    assert "platform" in d


def test_stable_run_id_deterministic():
    p = {"a": 1, "b": 2}
    a = stable_run_id(p)
    b = stable_run_id(p)
    assert a == b
    assert isinstance(a, str)
    assert len(a) >= 8


def test_now_utc_iso_format():
    s = now_utc_iso()
    assert "T" in s
    assert "Z" in s or "+" in s or "-" in s


def test_make_run_manifest_has_required_keys():
    m = make_run_manifest(
        name="test_run",
        args={"freq": "1h"},
        data_window={"n_assets": 3, "n_bars": 100},
        outputs={"/a": "sha1", "/b": "sha2"},
        metrics={"sharpe": 0.5},
        notes="",
    )
    for key in ("run_id", "created_utc", "git_commit", "env_fingerprint", "args", "data_window", "outputs", "metrics"):
        assert key in m


def test_save_manifest_writes_file():
    with tempfile.TemporaryDirectory() as tmp:
        m = make_run_manifest("t", {}, {}, {}, {}, "")
        path = save_manifest(tmp, m)
        assert Path(path).is_file()
        with open(path) as f:
            data = json.load(f)
        assert data.get("run_id") == m["run_id"]


def test_load_manifests_returns_dataframe():
    import pandas as pd

    with tempfile.TemporaryDirectory() as tmp:
        m = make_run_manifest("t", {}, {}, {}, {}, "")
        save_manifest(tmp, m)
        df = load_manifests(tmp)
    assert isinstance(df, pd.DataFrame)
    assert "run_id" in df.columns or df.empty


def test_snapshot_outputs_and_sha256():
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "f.txt"
        f.write_text("hello")
        h = compute_file_sha256(str(f))
        assert isinstance(h, str)
        assert len(h) == 64
        d = snapshot_outputs([str(f)])
        assert str(f) in d
        assert d[str(f)] == h


def test_snapshot_outputs_missing_file():
    d = snapshot_outputs(["/nonexistent/path/file.txt"])
    assert "/nonexistent/path/file.txt" in d
    assert d["/nonexistent/path/file.txt"] == ""
