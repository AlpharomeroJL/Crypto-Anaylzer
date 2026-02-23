# Refactor move map (scale-ready package layout)

**No behavior change.** Mechanical file moves, import updates, and compatibility shims only. No output drift, no artifact/DB schema changes, no CLI behavior changes.

## Target architecture

Incremental, behavior-preserving layout (packages created; implementations moved only when safe):

```
crypto_analyzer/
  core/          # RunContext, ExecContext, seeding, types, errors, hashing
  data/          # load_bars, load_snapshots, get_factor_returns, etc.
  artifacts/    # compute_file_sha256, ensure_dir, write_json_sorted, etc.
  stats/         # reality_check, calibration_*, RC/RW
  pipeline/      # Transform; re-exports run_research_pipeline, ResearchPipelineResult from pipelines
  pipelines/     # run_research_pipeline implementation
  governance/    # promote, evaluate_and_record, audit
  execution/     # (scaffolding; empty in this PR)
  compute/       # (scaffolding; empty in this PR)
```

Boundary rules: core must not import governance/store/cli/promotion; db must not import governance; store must not import core business logic.

## Moves done in this PR

- **Created** `crypto_analyzer/core/types.py` — shared typing aliases, Protocols only.
- **Created** `crypto_analyzer/core/errors.py` — shared exception types only (`CryptoAnalyzerError`).
- **Existing** `crypto_analyzer/core/hashing.py` — re-exports `compute_file_sha256` from artifacts; TODO placeholders only.
- **Existing** `crypto_analyzer/data/__init__.py` — stable import surface (`from crypto_analyzer.data import load_bars`).
- **Existing** `crypto_analyzer/artifacts/__init__.py` — stable import surface; unchanged.
- **Existing** `crypto_analyzer/stats/__init__.py` — façade re-exporting reality_check entrypoints.
- **Updated** `crypto_analyzer/pipeline/__init__.py` — façade now re-exports `run_research_pipeline`, `ResearchPipelineResult` from `crypto_analyzer.pipelines`.
- **Existing** `crypto_analyzer/governance/__init__.py` — canonical promote/audit entrypoints.
- **Existing** `crypto_analyzer/execution/__init__.py` — empty package scaffolding.
- **Created** `crypto_analyzer/compute/__init__.py` — empty package scaffolding.
- **Compatibility:** `crypto_analyzer/rng.py` remains shim to `crypto_analyzer.core.seeding`.
- **Tests:** `tests/test_import_compat_shims.py` added; `tests/test_no_illegal_imports.py` extended (core must not import promotion).

## Internal checklist (no behavior change)

- [ ] All tests pass: `pytest -m "not slow" -q --tb=short`
- [ ] Determinism tests pass (see below)
- [ ] Ruff: `ruff check .` and `ruff format .`
- [ ] No new migrations; no artifact key/schema changes

## Determinism / must-run tests (after each major batch)

- `tests/test_reportv2_deterministic_rerun.py` — byte-identical rerun
- `tests/test_reality_check_rng_determinism.py` — RC RNG determinism
- `tests/test_reality_check_deterministic.py` — RC determinism
- `tests/test_governance.py::test_stable_run_id_deterministic` — run_id determinism
- `tests/test_fold_spec_and_split_plan.py` — fold determinism
- `tests/test_migrations_phase3.py` — migrations idempotent
- Promotion/gating: `tests/test_promotion_gating.py`, `tests/test_promotion_service.py`

## Verification commands

```bash
python -m ruff check .
python -m ruff format .
python -m pytest -m "not slow" -q --tb=short
python -m pytest tests/test_reportv2_deterministic_rerun.py tests/test_reality_check_rng_determinism.py tests/test_reality_check_deterministic.py tests/test_migrations_phase3.py -q --tb=short
python -m pytest tests/test_import_compat_shims.py -q --tb=short
```

## Old path → new path mapping

| Old path | New path | Shim |
|----------|----------|------|
| (Step 1) | | |
| — | `crypto_analyzer/core/types.py` | — |
| — | `crypto_analyzer/core/errors.py` | — |
| — | `crypto_analyzer/core/hashing.py` (re-exports `artifacts.compute_file_sha256`) | — |
| — | `crypto_analyzer/core/seeding.py` (re-exports `rng`) | — |
| — | `crypto_analyzer/data/` (pkg) | — |
| — | `crypto_analyzer/execution/` (empty pkg) | — |
| `crypto_analyzer/data.py` | `crypto_analyzer/data/__init__.py` | N/A (same import path) |
| `crypto_analyzer/artifacts.py` | `crypto_analyzer/artifacts/__init__.py` | N/A (same import path) |
| (This PR: core canonical) | | |
| — | `crypto_analyzer/core/context.py` | canonical; no old path |
| — | `crypto_analyzer/core/__init__.py` | exports RunContext, ExecContext |
| `crypto_analyzer/rng.py` (impl) | `crypto_analyzer/core/seeding.py` (impl) | `crypto_analyzer/rng.py` → shim to core.seeding |
| — | `crypto_analyzer/core/hashing.py` | façade: compute_file_sha256; TODOs for stable_json_dumps, canonical_json_bytes |

## Compatibility shims

| Old path | New path (canonical) |
|----------|----------------------|
| `crypto_analyzer.rng` | `crypto_analyzer.core.seeding` (rng.py is shim) |
| (no legacy context) | `crypto_analyzer.core.context` |

- `crypto_analyzer.rng`: **shim** re-exporting from `crypto_analyzer.core.seeding` (canonical).
- Context: no legacy `crypto_analyzer.context`; canonical is `crypto_analyzer.core.context`.
- `crypto_analyzer.contracts`: unchanged; no move.
- `crypto_analyzer.governance`: audit already under governance/; no move.
- `crypto_analyzer.pipeline`: façade re-exporting `run_research_pipeline`, `ResearchPipelineResult` from `crypto_analyzer.pipelines`.

## Notes

- **RNG canonical:** `crypto_analyzer.core.seeding`. `crypto_analyzer.rng` is a shim.
- **Context canonical:** `crypto_analyzer.core.context`; exported from `crypto_analyzer.core`.
- **Hashing:** `crypto_analyzer.core.hashing` exports `compute_file_sha256`; artifacts unchanged.
- DB and migrations: not moved; optional `crypto_analyzer/data/db/` in a later PR.
- Import-compat: `tests/test_import_compat_shims.py` ensures rng/context shims resolve and are identical.
