# Refactor move map (scale-ready package layout)

**No behavior change.** Mechanical file moves, import updates, and compatibility shims only. No output drift, no artifact/DB schema changes, no CLI behavior changes.

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

## Shim list

- `crypto_analyzer.rng`: **shim** re-exporting from `crypto_analyzer.core.seeding` (canonical).
- Context: no legacy `crypto_analyzer.context`; canonical is `crypto_analyzer.core.context`.
- `crypto_analyzer.contracts`: unchanged; no move.
- `crypto_analyzer.governance`: audit already under governance/; no move.

## Notes

- **RNG canonical:** `crypto_analyzer.core.seeding`. `crypto_analyzer.rng` is a shim.
- **Context canonical:** `crypto_analyzer.core.context`; exported from `crypto_analyzer.core`.
- **Hashing:** `crypto_analyzer.core.hashing` exports `compute_file_sha256`; artifacts unchanged.
- DB and migrations: not moved; optional `crypto_analyzer/data/db/` in a later PR.
- Import-compat: `tests/test_import_compat_shims.py` ensures rng/context shims resolve and are identical.
