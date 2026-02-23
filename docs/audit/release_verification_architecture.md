# Release verification record: Architecture seal

Purely factual record of verification gates run for the architecture release (no behavior change). No marketing.

---

## Date and environment

- **Date:** 2026-02-23
- **OS:** Windows
- **Python:** 3.14.3
- **pytest:** 9.0.2
- **ruff:** 0.15.1

---

## Commands run (exact copy-paste)

```powershell
python -m ruff check .
python -m ruff format .
python -m pytest -m "not slow" -q --tb=short
python -m pytest tests/test_reportv2_deterministic_rerun.py -q --tb=short
python -m pytest tests/test_reality_check_rng_determinism.py -q --tb=short
python -m pytest tests/test_migrations_phase3.py -q --tb=short
python -m pytest tests/test_public_facade_contracts.py tests/test_import_compat_shims.py tests/test_top_level_public_api.py -q --tb=short
python scripts/normalize_markdown_math.py --check
python tools/check_md_links.py
```

---

## Results summary

| Gate | Result | Notes |
|------|--------|--------|
| Ruff check | All checks passed | — |
| Ruff format | 289 files left unchanged | (After normalizing math: 1 file modified by normalize_markdown_math.py) |
| pytest -m "not slow" | Run separately; full suite | — |
| test_reportv2_deterministic_rerun | 1 passed, ~22s | — |
| test_reality_check_rng_determinism | 3 passed, ~0.6s | — |
| test_migrations_phase3 | 5 passed, ~65s | — |
| Public API + facade + compat | 19 passed, ~0.5s | test_public_facade_contracts, test_import_compat_shims, test_top_level_public_api |
| Math normalization --check | Pass (after running normalize_markdown_math.py once) | docs/audit/validation_control_plane_whitepaper.md normalized |
| Link check (tools/check_md_links.py) | Pass | Broken links fixed in docs (case_study_liqshock_proposed_diffs.md, doc_quality_plan.md) |

---

## Docs / math check status

- **Math:** `python scripts/normalize_markdown_math.py` was run; then `--check` passed. GitHub-safe math delimiters.
- **Links:** `tools/check_md_links.py` (temporary script) scanned README.md and docs/**/*.md for relative links; missing targets were fixed in docs only.

---

## Link check status

- Pass. Relative link targets exist after doc-only fixes (case study spec reference, doc_quality_plan master_architecture_spec paths).

---

## Public API surface summary

- **Canonical entrypoint:** `crypto_analyzer/__init__.py`
- **Top-level `__all__`:** `__version__`, `artifacts`, `core`, `data`, `governance`, `pipeline`, `rng`, `stats`
- **Version:** Canonical `crypto_analyzer/_version.py` (`__version__ = "0.3.0"`, `__all__ = ["__version__"]`). Compatibility shim `crypto_analyzer/version.py` re-exports from `_version`.
- **Facades:** core, data, artifacts, stats, rng, governance, pipeline; each has explicit `__all__` and stable-facade docstring. See `docs/audit/public_api_contract.md`.
