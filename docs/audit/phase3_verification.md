# Phase 3 verification — proof artifacts

Run from repo root with venv activated: `.venv\Scripts\activate` (PowerShell).

---

## 1) Lint/format gate (ruff)

```powershell
ruff check .
ruff format .
ruff check .
```

**Result (2026-02-22):**

```
All checks passed!
---
269 files left unchanged
---
All checks passed!
```

---

## 2) Fast suite (CI-safe)

```powershell
python -m pytest -q -m "not slow" --tb=short
```

**Expected:** All tests pass (no failures).  
**Note:** Run locally and paste the final line here, e.g. `558 passed in 8m20s`.

---

## 3) Migrations test (Phase 3 tables/triggers)

```powershell
python -m pytest -q tests/test_migrations_phase3.py --tb=short
```

**Result (2026-02-22):**

```
.....                                                                    [100%]
5 passed in 64.61s (0:01:04)
```

---

## 4) Determinism smoke

```powershell
python -m pytest -q tests/test_reportv2_deterministic_rerun.py tests/test_reality_check_rng_determinism.py --tb=short
```

**Result (2026-02-22):**

```
....                                                                     [100%]
4 passed in 4.10s
```

---

## Green bar definition (Phase 3 done when…)

- [x] `ruff check .` passes after `ruff format .`
- [ ] `pytest -m "not slow"` passes (run and paste result above)
- [x] Migrations test green (`test_migrations_phase3.py`)
- [x] Determinism smoke green

---

*Update the "not slow" result line after running the full fast suite locally.*
