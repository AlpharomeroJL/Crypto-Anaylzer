# Public API contract

Stable facades, compatibility policy, and import boundaries. No behavior change when tightening; this doc is the single reference for "what is public" and "what must not be broken."

**Canonical entrypoint:** `crypto_analyzer/__init__.py` is the top-level public API. Prefer `import crypto_analyzer as ca` and then `ca.core`, `ca.data`, etc.

**Top-level `__all__` (names only):** `__version__`, `artifacts`, `core`, `data`, `governance`, `pipeline`, `rng`, `stats`.

**Version:** Canonical version file is `crypto_analyzer/_version.py`; it defines `__version__` and `__all__ = ["__version__"]`. `crypto_analyzer/version.py` is a compatibility shim that re-exports from `_version`; do not remove it without a deprecation cycle.

---

## Versioning / SemVer policy

- **MAJOR:** Breaking changes to names or behavior in `__all__` of `crypto_analyzer` or any facade (removals, renames, signature/behavior changes).
- **MINOR:** Additive exports (new names added) with backwards compatibility; no removals or breaking changes.
- **PATCH:** Internal changes and bug fixes that do not change public API behavior or surface.

Version is defined in `crypto_analyzer/_version.py` and re-exported as `crypto_analyzer.__version__`. The shim `crypto_analyzer.version` also exposes `__version__` for compatibility.

---

## Public surfaces (facades)

These modules are the **stable public API**. Consumers should import from them; implementations may move behind them.

| Module | Purpose | Import weight |
|--------|---------|----------------|
| `crypto_analyzer.core` | RunContext, ExecContext | Light (context only). |
| `crypto_analyzer.data` | load_bars, load_snapshots, get_factor_returns, etc. | Light (config, read_api). Does not import cli or promotion. |
| `crypto_analyzer.artifacts` | compute_file_sha256, ensure_dir, write_json_sorted, etc. | Light. Does not import cli or promotion. |
| `crypto_analyzer.stats` | run_reality_check, RealityCheckConfig, etc. | Light. Does not import cli or promotion. |
| `crypto_analyzer.rng` | seed_root, rng_for, rng_from_seed (shim to core.seeding) | Light. |
| `crypto_analyzer.governance` | promote, evaluate_and_record, run identity helpers | **Heavy:** intentionally imports promotion. Does not import cli. |
| `crypto_analyzer.pipeline` | Transform, run_research_pipeline, ResearchPipelineResult | **Heavy:** re-exports from pipelines, which imports promotion. |

Each facade must have:

- A module docstring stating it is a **stable facade** and what it does not import (or that it intentionally imports promotion).
- An explicit **`__all__`** listing every public name.
- A comment: **"Do not add exports without updating __all__."**

Scaffolding packages with intentionally empty APIs: `crypto_analyzer.execution`, `crypto_analyzer.compute`. They may have empty `__all__`; they are not consumer-facing facades.

---

## Internal modules

Everything under `crypto_analyzer/` that is not listed above as a public surface is **internal**. Callers may use it, but the project does not guarantee stability. Prefer importing from the facades. Internal modules may be reorganized or renamed in later PRs; facades are the compatibility boundary.

---

## Compatibility shims policy

- **What:** A shim is a module that re-exports from a canonical location so old import paths keep working (e.g. `crypto_analyzer.rng` → `crypto_analyzer.core.seeding`).
- **Where:** Shims live at the **old** path; canonical implementation lives at the **new** path. Do not remove the old path without a shim.
- **How long:** Shims remain until a major version or an explicit deprecation cycle; they are not removed in the same PR that introduces the canonical location.
- **Tests:** There must be tests that (1) the shim module imports successfully, and (2) the re-exported symbol is the same object as the canonical one (identity check). See `tests/test_import_compat_shims.py` and `tests/test_public_facade_contracts.py`. Version shim: `crypto_analyzer.version.__version__` must equal `crypto_analyzer._version.__version__` (see `tests/test_top_level_public_api.py`).

---

## Import boundary policy

Enforced by `tests/test_no_illegal_imports.py` and facade smoke tests:

- **core** must not import: governance, promotion, store, cli.
- **db** must not import: governance.
- **store** must not import: core business logic (e.g. promotion.gating, promotion.service), per existing store test.
- **governance** must not import: cli.

Facades that must stay "clean" (no cli, no promotion) when imported: **core, data, artifacts, stats, rng**. Pipeline and governance are allowed to depend on promotion by design.

---

## How to add new exports

1. **Choose the right facade** (or create a new package and add it to this doc).
2. **Implement** in the canonical module (do not put new logic in the facade file if it belongs elsewhere).
3. **Re-export** from the facade and append the name to **`__all__`**.
4. **Update the docstring** if the facade’s "import weight" or "does not import" claim changes.
5. **Add a test** in `tests/test_public_facade_contracts.py`: the test that checks `hasattr(module, name)` for every `__all__` name will fail until you add the new name to `__all__`; once added, the test validates the export.
6. **Run:** `pytest tests/test_public_facade_contracts.py tests/test_import_compat_shims.py tests/test_no_illegal_imports.py -q --tb=short`.

---

## Verification commands

```bash
python -m ruff check .
python -m ruff format .
python -m pytest -m "not slow" -q --tb=short
python -m pytest tests/test_public_facade_contracts.py tests/test_import_compat_shims.py tests/test_top_level_public_api.py -q --tb=short
```

See also [Refactor move map](refactor_move_map.md) for the target layout and shim list.
