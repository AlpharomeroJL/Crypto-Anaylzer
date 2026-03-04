# Plan: 100% sys.path cleanup + STRICT_SYSPATH_GUARD in CI

**PLAN MODE ONLY.** No file edits until this plan is approved and BUILD mode starts.

---

## Scope

- **Guard scan:** `tests/*.py` only (tests_dir.rglob("*.py")). `tools/*.py` are not scanned.
- **Goal:** Zero `sys.path.insert`/`sys.path.append` in tests; guard strict by default; CI sets `STRICT_SYSPATH_GUARD=1`.

---

## Commit 1: Remove all sys.path hacks in tests

**Purpose:** Remove every `sys.path.insert`/`append` and any `_root`/`ROOT` used only for path hacks. Replace `from cli import research_report_v2` with `from crypto_analyzer.cli.reportv2 import main` and fix patch targets to `crypto_analyzer.cli.reportv2.*`. Fix test_app_imports to use package import. Fix test_rng_central inline script to not use sys.path (rely on installed package).

**Files changed (by category):**

### 1a) Simple removal only (no cli/reportv2)

Remove the two lines: `_root = Path(__file__).resolve().parent.parent` (or equivalent) and `sys.path.insert(0, str(_root))` (or `sys.path.insert(0, str(ROOT))` / `if str(ROOT) not in sys.path: sys.path.insert(...)`). If `_root` is used elsewhere in the file for paths (e.g. out_dir), keep a local variable only where needed (e.g. inside a test) or use `Path(__file__).resolve().parent.parent` inline for that use.

**Files:**  
`test_alpha_research.py`, `test_api_smoke.py`, `test_cs_factors.py`, `test_cs_model.py`, `test_dataset_fingerprint.py`, `test_doctor.py`, `test_dynamic_beta_estimator.py`, `test_execution_cost.py`, `test_experiment_metadata.py`, `test_experiment_registry.py`, `test_experiment_store_sqlite.py`, `test_factor_residual_alignment.py`, `test_factors_causality.py`, `test_factors_stability.py`, `test_family_id_stable.py`, `test_hypothesis_id.py`, `test_leakage_sentinel.py`, `test_milestone4.py`, `test_multifactor_ols.py`, `test_optimizer_qp.py`, `test_portfolio_research.py`, `test_promotion_gating.py`, `test_promotion_requires_fold_causality_attestation.py`, `test_reality_check_deterministic.py`, `test_reality_check_null_sanity.py`, `test_regime_conditioning_no_leakage.py`, `test_regimes.py`, `test_reportv2_dataset_id.py`, `test_reportv2_walkforward_fold_causality.py`, `test_research_pipeline_smoke.py`, `test_residuals.py`, `test_returns_math.py`, `test_statistics_research.py`, `test_structural_breaks.py`.

**Example patch (test_alpha_research.py):**

```diff
--- a/tests/test_alpha_research.py
+++ b/tests/test_alpha_research.py
@@ -3,11 +3,8 @@
 import sys
 from pathlib import Path

-_root = Path(__file__).resolve().parent.parent
-sys.path.insert(0, str(_root))
-
 import numpy as np
 import pandas as pd
```

**Example patch (test_api_smoke.py):**

```diff
--- a/tests/test_api_smoke.py
+++ b/tests/test_api_smoke.py
@@ -8,8 +8,6 @@ import sys
 import pytest

-sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
-
 fastapi = pytest.importorskip("fastapi")
```

(Repeat for each file: delete the _root/ROOT line and the sys.path line; leave any other use of Path(__file__).parent.parent for out_dir etc. unchanged.)

### 1b) reportv2 tests: remove path hack + switch to crypto_analyzer.cli.reportv2 + fix patches

**Files:**  
`test_profile_timings_optional.py`, `test_reportv2_reality_check_optional.py`, `test_reportv2_factor_run_id_optional.py`, `test_reportv2_regime_conditioned_artifacts.py`, `test_reportv2_regimes_optional.py`, `run_golden_smoke_stats_stack.py`.

**Pattern for each:**
1. Remove `_root = Path(__file__).resolve().parent.parent` and `sys.path.insert(0, str(_root))`.
2. Keep `Path(__file__).resolve().parent.parent` only where used for out_dir (e.g. tmp_profile_off, tmp_profile_on).
3. Replace every `patch("cli.research_report_v2.get_research_assets", ...)` with `patch("crypto_analyzer.cli.reportv2.get_research_assets", ...)` (or remove if redundant with crypto_analyzer.research_universe.get_research_assets).
4. Replace `patch("cli.research_report_v2.get_factor_returns", ...)` with `patch("crypto_analyzer.cli.reportv2.get_factor_returns", ...)` (or `crypto_analyzer.data.get_factor_returns`).
5. Replace `patch("cli.research_report_v2.record_experiment_run", ...)` with `patch("crypto_analyzer.cli.reportv2.record_experiment_run", ...)`.
6. Replace `from cli import research_report_v2` + `research_report_v2.main()` with `from crypto_analyzer.cli.reportv2 import main` + `main()` (import can stay inside the with block).

**Example (test_profile_timings_optional.py):**

```diff
--- a/tests/test_profile_timings_optional.py
+++ b/tests/test_profile_timings_optional.py
@@ -10,9 +10,6 @@ from pathlib import Path
 import numpy as np
 import pandas as pd

-_root = Path(__file__).resolve().parent.parent
-sys.path.insert(0, str(_root))
-
 def _fake_returns_and_meta():
...
@@ -60,8 +57,8 @@ def test_profiling_off_no_timings_file():
     with patch.dict(os.environ, env, clear=False):
         with patch("crypto_analyzer.research_universe.get_research_assets", return_value=_fake_returns_and_meta()):
             with patch("crypto_analyzer.data.get_factor_returns", return_value=None):
                 sys.argv = argv
-                from cli import research_report_v2
-                research_report_v2.main()
+                from crypto_analyzer.cli.reportv2 import main
+                main()
     assert not timings_path.exists()
```

(And same for test_profiling_on_timings_written; out_dir already uses Path(__file__).resolve().parent.parent / "tmp_profile_on", keep that.)

**Example (run_golden_smoke_stats_stack.py):**

- Remove `_root` and `sys.path.insert(0, str(_root))`. Keep `_root` only if used for paths later; in this script _root is only for path hack, so remove both.
- In _run_report: change patches from `cli.research_report_v2.*` to `crypto_analyzer.cli.reportv2.*` (or keep only crypto_analyzer.research_universe.get_research_assets and add crypto_analyzer.data.get_factor_returns, crypto_analyzer.cli.reportv2.record_experiment_run). Replace `from cli import research_report_v2` + `research_report_v2.main()` with `from crypto_analyzer.cli.reportv2 import main` + `main()`.

### 1c) test_app_imports.py

- Remove ROOT and the entire block that does `if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))`.
- In test_import_app_without_streamlit_run: replace loading via spec_from_file_location(ROOT / "cli" / "app.py") with `import crypto_analyzer.cli.app as app` and assert hasattr(app, "main").

```diff
--- a/tests/test_app_imports.py
+++ b/tests/test_app_imports.py
@@ -6,16 +6,11 @@
 import sys
 from pathlib import Path

-# Repo root on path
-ROOT = Path(__file__).resolve().parent.parent
-if str(ROOT) not in sys.path:
-    sys.path.insert(0, str(ROOT))
-
 def test_import_doctor_without_runtime():
     ...
 def test_import_app_without_streamlit_run():
-    """Import app module without starting Streamlit (ensures no inline import shadowing)."""
-    import importlib.util
-    spec = importlib.util.spec_from_file_location("app", ROOT / "cli" / "app.py")
-    assert spec is not None and spec.loader is not None
-    app = importlib.util.module_from_spec(spec)
-    spec.loader.exec_module(app)
+    """Import app module without starting Streamlit (ensures no inline import shadowing)."""
+    import crypto_analyzer.cli.app as app
     assert hasattr(app, "main")
```

### 1d) test_rng_central.py

- The inline code in the subprocess does `sys.path.insert(0, {repr(str(root))})` then `from crypto_analyzer.rng import ...`. When tests run with venv, the subprocess uses the same Python (sys.executable) and can import crypto_analyzer without path hack. Remove the two lines from the inline string: `import sys` and `sys.path.insert(0, ...)`.

```diff
--- a/tests/test_rng_central.py
+++ b/tests/test_rng_central.py
@@ -66,9 +66,7 @@ def test_rng_reproducible_across_process():
     root = Path(__file__).resolve().parent.parent
     code = f"""
-import sys
-sys.path.insert(0, {repr(str(root))})
 from crypto_analyzer.rng import SALT_RC_NULL, rng_for
 r = rng_for('cross_process_rk', SALT_RC_NULL)
 vals = r.random(5).tolist()
```

(Keep `root` for cwd=str(root) in subprocess.run.)

**Commit 1 acceptance criteria:**
- `uv run python -m pytest tests/test_no_syspath_hacks.py -q` run with STRICT_SYSPATH_GUARD=1 must PASS (zero violations).
- `rg "sys\.path\.(insert|append)" tests/` returns no matches (except inside test_no_syspath_hacks.py docstring/code that defines the guard).
- `uv run python -m pytest -m "not slow" -q --tb=short` passes.

**Commands after Commit 1:**
```
uv run python -m ruff check .
uv run python -m ruff format --check .
uv run python -m pytest tests/test_no_syspath_hacks.py -q
$env:STRICT_SYSPATH_GUARD="1"; uv run python -m pytest tests/test_no_syspath_hacks.py -q
uv run python -m pytest -m "not slow" -q --tb=short
```

---

## Commit 2: Make sys.path guard strict (Option A) + docs

**Purpose:** Remove xfail branching; guard always raises AssertionError when violations exist. Update docs/audit/README.md to mark TODO completed.

### 2a) tests/test_no_syspath_hacks.py

- Remove `import os` and `import pytest` if only used for xfail.
- Remove the branch: when `hits` non-empty, always `raise AssertionError(msg)`.
- Simplify docstring: guard fails if any test file contains sys.path.insert/append; use package imports; no mention of STRICT_SYSPATH_GUARD.

**Patch:**

```diff
--- a/tests/test_no_syspath_hacks.py
+++ b/tests/test_no_syspath_hacks.py
@@ -1,21 +1,14 @@
-"""Regression guard: tests must not use sys.path.insert/append.
-
-Use package imports (e.g. crypto_analyzer.cli.*) instead. Default: violations
-are reported via xfail so the suite stays green while legacy hacks remain.
-Strict mode: set STRICT_SYSPATH_GUARD=1 to fail the test (and CI) on any
-violation. Enable strict locally to validate before enabling in CI.
-"""
+"""Regression guard: tests must not use sys.path.insert/append. Use package imports (e.g. crypto_analyzer.cli.*) instead."""
 
 from __future__ import annotations
 
-import os
 from pathlib import Path
-
-import pytest
 
 _FORBIDDEN = ("sys.path.insert(", "sys.path.append(")
 _THIS_FILE = Path(__file__).resolve()
@@ -35,9 +28,7 @@ def test_no_syspath_hacks_in_tests():
     msg = "Forbidden sys.path hacks found. Use package imports (e.g. crypto_analyzer.cli.*) instead.\n"
     if hits:
         msg += "\n".join(f"  {path}:{line_no}: {snippet}" for path, line_no, snippet in hits)
-        if os.environ.get("STRICT_SYSPATH_GUARD") == "1":
-            raise AssertionError(msg)
-        pytest.xfail(reason=msg)
+        raise AssertionError(msg)
     assert True
```

### 2b) docs/audit/README.md

- Replace the TODO line with: "All sys.path hacks removed; STRICT_SYSPATH_GUARD=1 enforced in CI."

**Patch:**

```diff
--- a/docs/audit/README.md
+++ b/docs/audit/README.md
@@ -8,4 +8,4 @@ Use this folder for architecture audits, doc-upgrade checklists, and related arti
 Use this folder for architecture audits, doc-upgrade checklists, and related artifacts.
 
-- **TODO:** Remove remaining sys.path hacks in tests; then enable `STRICT_SYSPATH_GUARD=1` in CI.
+- **Completed:** All sys.path hacks removed; STRICT_SYSPATH_GUARD=1 enforced in CI.
```

**Commit 2 acceptance criteria:**
- test_no_syspath_hacks fails (AssertionError) if any violation is introduced; passes when clean.
- docs/audit/README.md no longer says TODO for this item.

---

## Commit 3: Enable STRICT_SYSPATH_GUARD=1 in CI

**Purpose:** Set env for pytest step so CI enforces the guard (and repo is clean, so step passes).

### .github/workflows/ci.yml

- Add env to the Pytest step: `STRICT_SYSPATH_GUARD: "1"`.
- Remove or update the comment that said "STRICT_SYSPATH_GUARD not set".

**Patch:**

```diff
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -52,8 +52,9 @@ jobs:
       - name: Ruff format check
         run: uv run ruff format --check .
 
-      # Pytest: STRICT_SYSPATH_GUARD not set; sys.path guard runs in xfail mode until legacy hacks removed.
-      # Full non-slow suite must complete; step fails if pytest fails or times out
       - name: Pytest (not slow)
+        env:
+          STRICT_SYSPATH_GUARD: "1"
         run: uv run pytest -m "not slow" -q --tb=short
         timeout-minutes: 20
```

**Commit 3 acceptance criteria:**
- Local run with STRICT_SYSPATH_GUARD=1: pytest -m "not slow" and test_no_syspath_hacks both pass.
- CI workflow file contains STRICT_SYSPATH_GUARD: "1" for the pytest step.

---

## Build checklist (after applying plan)

1. `uv run python -m ruff check .`
2. `uv run python -m ruff format --check .`
3. `uv run python -m pytest tests/test_no_syspath_hacks.py -q`
4. `uv run python -m pytest -m "not slow" -q --tb=short`
5. `rg "sys\.path\.(insert|append)" tests/` → no matches (or only in test_no_syspath_hacks.py for the guard definition/docstring)

---

## Verify checklist (expected results)

- Ruff: All checks passed; 320 files already formatted (or current count).
- test_no_syspath_hacks: 1 passed.
- pytest -m "not slow": all passed, 1 xfailed removed (guard now strict pass).
- rg: no hits in tests/ for sys.path.insert/append except the guard file’s own strings.

---

## Summary of files that had sys.path hacks (for final summary)

| File | Change |
|------|--------|
| test_alpha_research.py | Removed _root + sys.path.insert; already used crypto_analyzer.alpha_research |
| test_api_smoke.py | Removed sys.path.insert; already used crypto_analyzer.api |
| test_app_imports.py | Removed ROOT/path hack; replaced spec_from_file_location with import crypto_analyzer.cli.app |
| test_cs_factors.py, test_cs_model.py, test_dataset_fingerprint.py, test_doctor.py, test_dynamic_beta_estimator.py, test_execution_cost.py, test_experiment_metadata.py, test_experiment_registry.py, test_experiment_store_sqlite.py, test_factor_residual_alignment.py, test_factors_causality.py, test_factors_stability.py, test_family_id_stable.py, test_hypothesis_id.py, test_leakage_sentinel.py, test_milestone4.py, test_multifactor_ols.py, test_optimizer_qp.py, test_portfolio_research.py, test_promotion_gating.py, test_promotion_requires_fold_causality_attestation.py, test_reality_check_deterministic.py, test_reality_check_null_sanity.py, test_regime_conditioning_no_leakage.py, test_regimes.py, test_reportv2_dataset_id.py, test_reportv2_walkforward_fold_causality.py, test_research_pipeline_smoke.py, test_residuals.py, test_returns_math.py, test_statistics_research.py, test_structural_breaks.py | Removed _root + sys.path.insert; imports already package imports |
| test_profile_timings_optional.py, test_reportv2_reality_check_optional.py, test_reportv2_factor_run_id_optional.py, test_reportv2_regime_conditioned_artifacts.py, test_reportv2_regimes_optional.py, run_golden_smoke_stats_stack.py | Removed path hack; from crypto_analyzer.cli.reportv2 import main; patch targets to crypto_analyzer.cli.reportv2.* (or crypto_analyzer.data.get_factor_returns where appropriate) |
| test_rng_central.py | Removed sys.path.insert from inline subprocess -c string; package import only |

---

## Risks / follow-ups

- **run_golden_smoke_stats_stack.py** is a script run by hand (`python tests/run_golden_smoke_stats_stack.py`); caller must have package installed (e.g. venv with editable install). No change to that contract.
- **tools/** (check_experiments.py, sanity_check.py, sanity_check_m5.py) still contain sys.path.insert; they are not scanned by the guard. Optional follow-up: remove from tools/ for consistency.
- If any test imports a module that itself adds sys.path, that would still be a violation if that code lives under tests/; the guard only scans test file source, not runtime behavior of imported packages.
