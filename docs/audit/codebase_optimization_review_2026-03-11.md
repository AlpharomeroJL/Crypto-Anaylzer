# Codebase Optimization Review (2026-03-11)

This review summarizes high-impact opportunities to improve correctness, maintainability, and developer velocity.

## What was checked

- `ruff check crypto_analyzer cli tests tools`
- `python tools/check_md_links.py`
- Targeted test import/smoke commands (see Notes)

## Immediate fixes completed in this pass

1. **Resolved test lint drift (import sorting):**
   - `tests/test_governance.py`
   - `tests/test_import_compat_shims.py`
   - `tests/test_public_facade_contracts.py`

## Findings and proposed comprehensive change list

### P0 — Reliability / CI determinism

1. **Enforce package importability in test/verification commands**
   - Problem: direct `pytest` and tooling calls fail unless `crypto_analyzer` is installed or `PYTHONPATH` is configured.
   - Change: standardize commands via `python -m pytest` plus a single bootstrap (`uv run ...` in docs + CI), or add explicit `PYTHONPATH=.` in local helper scripts.

2. **Make dependency bootstrap robust for restricted networks**
   - Problem: dependency install attempts can fail in proxied/offline environments.
   - Change: add an offline/dev note (wheelhouse or `uv sync --frozen` path) and a deterministic fallback section in `README.md` + `CONTRIBUTING.md`.

3. **Add a fast pre-commit quality gate**
   - Problem: sortable import drift reached repository state.
   - Change: wire `ruff check --fix` + `ruff format --check` (if formatting is adopted) in pre-commit and CI required checks.

### P1 — Developer experience / maintainability

4. **Define and publish a canonical local verification command set**
   - Change: one documented sequence for contributors:
     1) lint
     2) fast tests subset
     3) smoke/doctor path
   - Keep command parity across README, CONTRIBUTING, and CI workflow.

5. **Consolidate duplicated tooling behavior**
   - Problem: many `tools/check_*.py` scripts likely overlap in environment/bootstrap behavior.
   - Change: add a small shared helper for CLI parsing, project-root resolution, and consistent error codes/messages.

6. **Normalize project naming typo across user-facing docs over time**
   - Problem: repository and title currently use `Crypto-Anaylzer` spelling.
   - Change: introduce a staged rename plan (docs aliases first, package/distribution compatibility shims, then final rename) to avoid ecosystem breakage.

### P2 — Quality scaling / architecture hygiene

7. **Risk-based test stratification**
   - Change: formalize `unit`, `integration`, `slow`, `network` markers and ensure default CI path runs deterministic non-network tests first.

8. **Dependency boundary enforcement expansion**
   - Change: extend existing architecture-boundary checks to include import-linter style contracts for newer modules (e.g., promotion/governance/read APIs).

9. **Observability for governance flows**
   - Change: add a compact, machine-readable report summary for promotion eligibility and gating outcomes, useful for CI artifacts and audits.

10. **Performance baselines for critical paths**
   - Change: add repeatable micro-benchmarks/smoke timings for dataset hash computation, fold splits, and report generation to detect regressions early.

## Suggested execution roadmap

- **Week 1 (stabilize):** items 1-3.
- **Week 2 (DX):** items 4-6.
- **Week 3+ (scale):** items 7-10.

## Notes

- In this environment, full test execution was limited by missing third-party dependencies (for example, `numpy`) when importing the package.
- Markdown link integrity check passed successfully.
