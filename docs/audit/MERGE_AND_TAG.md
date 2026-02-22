# Phase 3 — merge and tag instructions

Phase 3 work is currently **on `main`** as uncommitted changes (no separate branch). Use one of the two flows below.

---

## Option A: Commit on main and push (current state)

If you are happy to have Phase 3 as a single commit on `main`:

```powershell
cd "C:\Users\jo312\OneDrive\Desktop\Github Projects\Crypto-Anaylzer"
.venv\Scripts\activate

# 1) Stage all Phase 3 changes
git add -A
git status   # review

# 2) Commit (conventional message)
git commit -m "feat(phase3): productization, governance boundary, lineage, plugins, DuckDB backend"

# 3) Push main
git push origin main

# 4) Tag the milestone (version from crypto_analyzer/__init__.py, e.g. 0.3.0)
git tag v0.3-phase3
git push origin v0.3-phase3
```

---

## Option B: Create a branch, push, then merge to main

If you prefer a Phase 3 branch and then merge (e.g. for PR review):

```powershell
cd "C:\Users\jo312\OneDrive\Desktop\Github Projects\Crypto-Anaylzer"
.venv\Scripts\activate

# 1) Create branch from current main (with uncommitted work)
git checkout -b phase3-productization
git add -A
git commit -m "feat(phase3): productization, governance boundary, lineage, plugins, DuckDB backend"

# 2) Push branch
git push origin phase3-productization

# 3) Open PR: phase3-productization -> main; merge (squash or merge commit per your policy)

# 4) After merge, on main:
git checkout main
git pull origin main

# 5) Tag the milestone
git tag v0.3-phase3
git push origin v0.3-phase3
```

---

## Verification before push

```powershell
ruff check .
ruff format .
ruff check .
python -m pytest -q -m "not slow" --tb=short
python -m pytest -q tests/test_migrations_phase3.py --tb=short
python -m pytest -q tests/test_reportv2_deterministic_rerun.py tests/test_reality_check_rng_determinism.py --tb=short
```

All should pass. Proof can be recorded in `docs/audit/phase3_verification.md`.

---

## Tag version

- Use the same version as in `crypto_analyzer/__init__.py` (`__version__`). Current: **0.3.0**.
- Tag format: **`v0.3-phase3`** (lightweight tag for Phase 3 milestone).
- Push tag: **`git push origin v0.3-phase3`**.
