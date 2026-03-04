# Plan: Hermetic test_profile_timings_optional (eliminate flake)

## Diagnosis

**Root cause (confirmed):**
1. **Patch target**: Tests patched `crypto_analyzer.research_universe.get_research_assets`. When the full suite runs, `crypto_analyzer.cli.reportv2` is often already imported; reportv2 holds a direct reference to `get_research_assets` from import time. Patching the name in `research_universe` does not change reportv2’s reference, so reportv2 still called the real implementation. With `:memory:` DB that yields empty data, `n_assets < 1` and main() returns 0 before the timings write.
2. **Shared output dirs**: Fixed paths under repo root (`tmp_profile_off`, `tmp_profile_on`) could be reused or touched by other runs; not the primary cause but removed for isolation.
3. **Env**: Using monkeypatch for CRYPTO_ANALYZER_PROFILE ensures env is set/restored per test.

**Fix:** Use `tmp_path` and monkeypatch, and patch where the code under test looks up the functions: `crypto_analyzer.cli.reportv2.get_research_assets` and `crypto_analyzer.cli.reportv2.get_factor_returns`.

## Commit 1: Make tests hermetic (tmp_path + monkeypatch)

**File:** `tests/test_profile_timings_optional.py`

**Changes:**
- Add `tmp_path` (pytest fixture) to both tests.
- Use `out_dir = tmp_path / "profile_off"` and `out_dir = tmp_path / "profile_on"` instead of repo-root paths.
- Use `monkeypatch.setenv("CRYPTO_ANALYZER_PROFILE", "1")` and `monkeypatch.delenv("CRYPTO_ANALYZER_PROFILE", raising=False)` for the on/off tests so env is set only for the test and restored automatically.
- Remove the manual `if timings_path.exists(): timings_path.unlink()` since we use a fresh dir each time.
- Keep the same patches (get_research_assets, get_factor_returns) and the same assertions (timings.json exists, has "stages" and "run_id").

**Patch-style diff:**

```diff
--- a/tests/test_profile_timings_optional.py
+++ b/tests/test_profile_timings_optional.py
@@ -28,10 +28,9 @@ def _fake_returns_and_meta():
     return returns_df, meta_df


-def test_profiling_off_no_timings_file():
+def test_profiling_off_no_timings_file(tmp_path):
     """When CRYPTO_ANALYZER_PROFILE is not set, timings.json is not written."""
-    out_dir = Path(__file__).resolve().parent.parent / "tmp_profile_off"
-    out_dir.mkdir(parents=True, exist_ok=True)
+    out_dir = tmp_path / "profile_off"
+    out_dir.mkdir(parents=True, exist_ok=True)
     timings_path = out_dir / "timings.json"
-    if timings_path.exists():
-        timings_path.unlink()
-    env = os.environ.copy()
-    env.pop("CRYPTO_ANALYZER_PROFILE", None)
+    monkeypatch.delenv("CRYPTO_ANALYZER_PROFILE", raising=False)
     argv = [...]
-    with patch.dict(os.environ, env, clear=False):
+    with patch(...):
         ...
     assert not timings_path.exists()
```

(Full patch below in BUILD section.)

**Acceptance:** Both tests pass; no writes under repo root; env restored after test.

## Commit 2 (only if needed): reportv2 robustness

- Current code already writes timings in a dedicated block and uses `ensure_dir` via `write_json_sorted`. No change unless Commit 1 is insufficient.
- If we want extra safety: resolve `out_dir` to absolute at the start of the timings block and call `ensure_dir(out_dir)` before writing. Optional.

## Verification commands

```
python -m pytest tests/test_profile_timings_optional.py -q
python -m pytest -m "not slow" -q --tb=short
python -c "import subprocess, sys; [subprocess.run([sys.executable,'-m','pytest','tests/test_profile_timings_optional.py','-q'], check=True) for _ in range(10)]"
```

## Acceptance criteria

- test_profiling_off_no_timings_file and test_profiling_on_timings_written both pass.
- No use of fixed paths under repo root (tmp_profile_off, tmp_profile_on).
- Env controlled via monkeypatch.
- Full suite "not slow" passes including these tests.
- 10× repeated run of the profile timings tests passes.
