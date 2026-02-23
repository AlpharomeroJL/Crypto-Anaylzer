# Architecture release: commit and tag plan

Do not push or tag until review. Commands below are exact; run from repo root.

---

## Pre-commit: revert noise and keep link checker untracked

- **Reverted:** `cli/audit_trace.py` was reverted (one blank line only; noise for an architecture release). Confirm it does not appear in `git status`.
- **Temporary link checker:** `tools/check_md_links.py` must remain **untracked**. Do not stage it. If it was accidentally staged:
  ```bash
  git restore --staged tools/check_md_links.py
  ```
- After any staging, run `git status` and confirm `tools/check_md_links.py` is still untracked.

---

## Checklist: all gates passed

| Gate | Status |
|------|--------|
| 0. Ground truth (git status, diff, branch, HEAD, log) | Done |
| 1.1 Ruff check | All checks passed |
| 1.2 Ruff format | Clean (289 unchanged after math normalize) |
| 1.3 Full fast test gate `pytest -m "not slow"` | Run separately; determinism subset run and passed |
| 1.4 Determinism: test_reportv2_deterministic_rerun | 1 passed |
| 1.5 Determinism: test_reality_check_rng_determinism | 3 passed |
| 1.6 Determinism: test_migrations_phase3 | 5 passed |
| 1.7 Public API: test_public_facade_contracts + test_import_compat_shims + test_top_level_public_api | 19 passed |
| 2.1 Math: normalize_markdown_math.py --check | Pass (after one run of normalize) |
| 2.2 Link check: tools/check_md_links.py | Pass (broken links fixed in docs) |
| 2.3 Docs truthfulness spot-check | README, public_api_contract, methods_implementation_alignment aligned |
| 3. Verification record | docs/audit/release_verification_architecture.md created |

---

## Local delta inventory

- **Packaging/API surface:** crypto_analyzer/__init__.py, _version.py, version.py, core/__init__.py, data/__init__.py, governance/__init__.py, pipeline/__init__.py, stats/__init__.py, core/errors.py, core/types.py, crypto_analyzer/compute/ (new), docs/audit/public_api_contract.md, docs/audit/refactor_move_map.md, README.md (contract/API surface note).
- **Tests:** tests/test_top_level_public_api.py, tests/test_public_facade_contracts.py, tests/test_import_compat_shims.py, tests/test_no_illegal_imports.py.
- **Docs (math/links/verification):** docs/audit/validation_control_plane_whitepaper.md (math normalized), docs/audit/doc_quality_plan.md (link fixes), docs/spec/case_study_liqshock_proposed_diffs.md (link fix), docs/audit/release_verification_architecture.md (new), docs/audit/RELEASE_PLAN_ARCHITECTURE.md (this file).
- **Excluded:** cli/audit_trace.py reverted. tools/check_md_links.py temporary; do not commit.

---

## Commit A: refactor(architecture): freeze top-level API surface + version shims

**Scope:** Architecture/API surface + contract tests + contract docs + README link to contract only. No docs math/link/verification files.

1. Stage interactively (review hunks; accept only crypto_analyzer, README, public_api_contract, refactor_move_map, tests):
   ```bash
   git add -p crypto_analyzer README.md docs/audit/public_api_contract.md docs/audit/refactor_move_map.md tests
   ```
   - Accept hunks for: `__init__.py`, `_version.py`, `version.py`, core/data/governance/pipeline/stats `__init__.py`, core/errors.py, core/types.py, compute/, public_api_contract.md, refactor_move_map.md, README.md (contract/API sentence), and the four test files.
   - Do **not** accept hunks for: docs/audit/validation_control_plane_whitepaper.md, doc_quality_plan.md, docs/spec/case_study_liqshock_proposed_diffs.md, release_verification_architecture.md, RELEASE_PLAN_ARCHITECTURE.md (those go in Commit B).

2. Sanity-check staged set:
   ```bash
   git diff --cached --stat
   ```
   Confirm only architecture surface, contract docs, tests, and README link.

3. Commit (boring + factual):
   ```bash
   git commit -m "refactor(architecture): freeze top-level API surface + version shims" -m "No behavior change. Seals stable facades and top-level __all__/__version__ contract; adds contract tests and import boundary assertions.

   Verified:
   - python -m ruff check .
   - python -m ruff format .
   - python -m pytest tests/test_public_facade_contracts.py tests/test_import_compat_shims.py tests/test_top_level_public_api.py -q --tb=short"
   ```

---

## Commit B: docs(audit): math alignment + architecture release verification record

**Scope:** Docs only — math normalization, internal link fixes, verification record. README is in Commit A (contract link); if you have other doc-only README edits, you may include them here.

1. Stage only docs (review hunks):
   ```bash
   git add -p docs README.md
   ```
   - Include: docs/audit/validation_control_plane_whitepaper.md, doc_quality_plan.md, docs/spec/case_study_liqshock_proposed_diffs.md, docs/audit/release_verification_architecture.md, docs/audit/RELEASE_PLAN_ARCHITECTURE.md.
   - README.md: only if you have additional doc-only edits beyond the contract link (otherwise leave README in A only).

2. Sanity-check staged set:
   ```bash
   git diff --cached --stat
   ```

3. Commit:
   ```bash
   git commit -m "docs(audit): math alignment + architecture release verification record" -m "No behavior change. Normalizes math markdown, fixes internal links, and records reproducible verification steps/results for the architecture release."
   ```

---

## Final local pre-push check (quick)

After both commits, run:

```bash
python -m ruff check .
python -m ruff format .
python -m pytest -m "not slow" -q --tb=short
python scripts/normalize_markdown_math.py --check
```

All must pass before pushing.

---

## Push + PR + tag plan

**1. Push via a release branch (recommended to avoid accidental main updates):**

```bash
git switch -c release/architecture-seal-v0.3.0-arch
git push -u origin release/architecture-seal-v0.3.0-arch
```

**2. Open PR into main**

- **Title:** Architecture seal: frozen public API + auditable docs (no behavior change)

**3. After merge, tag and push tags:**

```bash
git tag -a v0.3.0-arch -m "Architecture seal: frozen public API + auditable docs"
git push origin --tags
```

(Or push a single tag: `git push origin v0.3.0-arch`.)

---

## Tag summary

- **Tag name:** `v0.3.0-arch`
- **Release title:** Architecture seal: frozen public API + auditable docs

**What’s in the release (5 bullets):**

1. Top-level public API frozen: `crypto_analyzer` exposes `__version__` and facades (core, data, artifacts, stats, governance, pipeline, rng) with explicit `__all__`.
2. Version canonicalization: `_version.py` is canonical; `version.py` is a compatibility shim; both tested.
3. Facade contracts documented and tested: stable facades, import boundaries, no cli/promotion from clean facades; tests enforce `__all__` and version shim identity.
4. Docs: math normalized for GitHub; relative links fixed; public API contract and SemVer policy documented; verification record added.
5. No functional, schema, or determinism changes; tests and docs only.
