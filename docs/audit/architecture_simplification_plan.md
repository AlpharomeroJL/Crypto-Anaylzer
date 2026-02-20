# Architecture simplification plan

Bounded refactor plan derived from `architecture_integrity_audit.md` and `drift_register.md`. **DOC-ONLY: no code edits.** Default behavior remains unchanged unless a slice explicitly states a behavior change and acceptance criteria.

---

## Top 5 flow problems (precise, code-referenced)

1. **Dual factor path: reportv2 bypasses materialized factors**  
   - **Where:** `cli/research_report_v2.py` builds factors in-memory via `build_factor_matrix` and `rolling_multifactor_ols` (from `crypto_analyzer/factors.py`). It does not read from `factor_model_runs` / `factor_betas` / `residual_returns` written by `crypto_analyzer/factor_materialize.materialize_factor_run`.  
   - **Effect:** Cache and reproducibility benefits of factor materialization are unused on the main report path; duplicate compute when both reportv2 and factor_materialize are run.  
   - **Ref:** Drift D2; audit “Spec vs implementation” Factor row; duplication inventory (OLS/factor).

2. **Cost application has multiple call sites; one canonical path**  
   - **Where:** `crypto_analyzer/portfolio.apply_costs_to_portfolio` delegates to `execution_cost.apply_costs`; `cli/backtest.py` constructs `ExecutionCostConfig` and `slippage_bps_from_liquidity` and calls `model.apply_costs`; `cli/app.py` and `crypto_analyzer/walkforward.py` pass `fee_bps`/`slippage_bps` and call `apply_costs_to_portfolio`. No single entry that all paths are audited to use.  
   - **Effect:** Risk of a future path bypassing ExecutionCostModel (e.g. ad-hoc bps formula); duplicated parameter passing.  
   - **Ref:** Audit duplication (cost application); drift I2.

3. **Integrity: warn vs hard-block undefined**  
   - **Where:** `crypto_analyzer/integrity.py` (e.g. `assert_monotonic_time_index`, `assert_no_negative_or_zero_prices`) returns warning strings or raises in some call paths; `cli/research_report_v2.py` uses `--strict-integrity` for bad row rate but alignment/index checks are not consistently “exit non-zero” vs “warn only.”  
   - **Effect:** Misaligned signal/return indices can produce silent NaNs; no contract on which failures are fatal.  
   - **Ref:** Drift D3; audit recommendation #6.

4. **Walk-forward does not re-fit factors per fold**  
   - **Where:** In `cli/research_report_v2.py` the walk-forward backtest path uses the same full-series factor build (get_research_assets → build_factor_matrix → rolling_multifactor_ols) for all folds; factor fitting is not restricted to train window per fold.  
   - **Effect:** Theoretically uses information from beyond the train window when computing betas used in test; spec says factor fitting must be restricted to available history per fold.  
   - **Ref:** Drift D6; audit leakage inventory “Factor per-fold.”

5. **Legacy report and CLIs call residual/OLS without single contract**  
   - **Where:** `cli/research_report.py` calls `signal_residual_momentum_24h(returns_df, args.freq)` (no explicit `allow_lookahead=False`). `cli/scan.py`, `cli/analyze.py`, `cli/report_daily.py` call `compute_ols_betas` or factor/signal helpers; OLS/residual logic is spread across factors.py, alpha_research.py, and CLI scripts.  
   - **Effect:** Residual path is safe by default but not explicitly guarded in research_report.py; OLS usage in scan/analyze/report_daily could drift from factors contract if someone reimplements.  
   - **Ref:** Drift D5; audit duplication (OLS/residual); recommendation #12.

---

## Proposed refactor slices (6–10 max)

### Slice 1: Explicit residual guard and cost-path audit (no behavior change)

| Item | Detail |
|------|--------|
| **Scope** | Add explicit `allow_lookahead=False` in the single residual call in research_report.py; document that all cost application must go through `crypto_analyzer/execution_cost` (audit only in this slice—no code change to app/walkforward beyond comments if desired). |
| **Files touched** | `cli/research_report.py` (one argument added). Optional: one-line comment in `cli/app.py`, `crypto_analyzer/walkforward.py` stating “cost path: execution_cost only.” |
| **Interfaces affected** | None (same function signature; default already False). |
| **Tests to add/adjust** | None required. Optional: assert in test that research_report never calls signal_residual_momentum_24h with allow_lookahead=True (e.g. grep or small test). |
| **Rollback** | Revert single line in research_report.py. |
| **Behavior** | **No behavior change.** Acceptance: report output unchanged for same inputs; residual remains causal. |

---

### Slice 2: Integrity hard-block policy (behavior change)

| Item | Detail |
|------|--------|
| **Scope** | Define which integrity checks are “hard-block” (exit non-zero) vs “warn only.” Implement hard-block for: (1) index non-monotonic when strict mode, (2) signal/return index misalignment in reportv2 validation path. Leave “bad row rate” as already gated by --strict-integrity. |
| **Files touched** | `crypto_analyzer/integrity.py` (e.g. new function or flag: `assert_*_strict` that raises or returns exit code); `cli/research_report_v2.py` (call strict check before validation; exit 4 or documented code on failure). |
| **Interfaces affected** | New or extended integrity API (e.g. `check_alignment_strict(signal_df, returns_df) -> Optional[str]` with None = OK, str = error message for exit). |
| **Tests to add/adjust** | Add test: when indices misaligned and strict mode, reportv2 exits non-zero. Add test: when monotonicity violated and strict, exit non-zero. Adjust any test that currently relies on “warn only” in those code paths. |
| **Rollback** | Revert integrity.py and reportv2 changes; restore warn-only behavior. |
| **Behavior** | **Behavior change.** Acceptance: (1) With --strict-integrity (or new --strict-alignment), reportv2 exits non-zero if time index non-monotonic or signal/return indices misaligned. (2) Without strict flag, behavior unchanged (warn only). (3) Doc in pipeline_contracts: “Where errors are handled vs surfaced” lists hard-block conditions. |

---

### Slice 3: Reportv2 optional “use materialized factor run” (no default change)

| Item | Detail |
|------|--------|
| **Scope** | Add optional CLI flag (e.g. `--factor-run-id`) to reportv2. When set, load betas/residuals from factor_betas and residual_returns for that factor_run_id instead of computing in-memory with build_factor_matrix + rolling_multifactor_ols. Default: unset = current behavior (in-memory). |
| **Files touched** | `cli/research_report_v2.py` (arg parse; branch: if factor_run_id set, load from DB via new or existing data accessor); `crypto_analyzer/data.py` or new `crypto_analyzer/factor_materialize.py` helper (e.g. `load_factor_run(conn, factor_run_id)` returning aligned factor/residual panels). |
| **Interfaces affected** | New: load_factor_run(conn, factor_run_id) → (betas_dict or aligned panel, residual_df, metadata). reportv2 internal: two code paths (in-memory vs from DB). |
| **Tests to add/adjust** | Add test: with --factor-run-id and a pre-materialized run, reportv2 produces same signal/validation outputs (or documented equivalence). Add test: invalid factor_run_id exits or warns clearly. |
| **Rollback** | Remove flag and branch; reportv2 always in-memory. |
| **Behavior** | **No behavior change by default.** Acceptance: (1) Without --factor-run-id, behavior identical to today. (2) With valid --factor-run-id, report uses materialized factors and matches (or documents) equivalence to in-memory. |

---

### Slice 4: Engine and config version in manifest and experiments (no behavior change)

| Item | Detail |
|------|--------|
| **Scope** | Add engine_version and config_version to manifest (governance.make_run_manifest) and to experiments table (record_experiment_run). Read from spec or config (e.g. spec_version already present; add config_version from config.yaml if present, else “”). |
| **Files touched** | `crypto_analyzer/governance.py` (make_run_manifest: add engine_version, config_version); `crypto_analyzer/experiments.py` (record_experiment_run: add columns if not present); `crypto_analyzer/db/migrations.py` or migrations_v2.py (guarded ALTER TABLE for experiments.engine_version, experiments.config_version). |
| **Interfaces affected** | Manifest dict and experiments row schema (add two optional fields). |
| **Tests to add/adjust** | Add test: manifest JSON contains engine_version and config_version when produced. Add test: experiment row contains new columns when written. Backward compat: existing DBs without columns still work (nullable or default “”). |
| **Rollback** | Remove ALTER and writes; revert manifest shape. |
| **Behavior** | **No behavior change** (additive metadata). Acceptance: existing runs still succeed; new runs store and display engine_version and config_version. |

---

### Slice 5: Single cost entry point (no behavior change)

| Item | Detail |
|------|--------|
| **Scope** | Ensure every call path that applies costs uses `crypto_analyzer/execution_cost.apply_costs` or `ExecutionCostModel.apply_costs` (or portfolio.apply_costs_to_portfolio which delegates to it). Audit: app.py, walkforward.py, reportv2, backtest. No new logic; refactor any direct fee/slippage formula to call execution_cost. |
| **Files touched** | `cli/app.py`, `crypto_analyzer/walkforward.py`, `cli/research_report_v2.py`, `cli/backtest.py` (only if any path uses ad-hoc cost math; audit first). |
| **Interfaces affected** | None if already delegating; if a path is found that does not delegate, replace with call to apply_costs_to_portfolio or apply_costs. |
| **Tests to add/adjust** | Existing test_execution_cost.py and integration tests remain. Add or extend test: “all cost application paths go through execution_cost module” (e.g. grep test or small harness). |
| **Rollback** | Revert any call-site change to previous formula/call. |
| **Behavior** | **No behavior change.** Acceptance: net returns and cost breakdown unchanged for same inputs; all paths documented as using ExecutionCostModel. |

---

### Slice 6: Pytest mark for reportv2 full-run tests (no behavior change)

| Item | Detail |
|------|--------|
| **Scope** | Mark tests that invoke reportv2.main() (or full reportv2 stack) with a pytest mark, e.g. `@pytest.mark.integration` or `@pytest.mark.reportv2_full`, so they can be run separately (e.g. `pytest -m "not integration"` for fast unit runs). |
| **Files touched** | `tests/test_reportv2_deterministic_rerun.py`, `tests/test_reportv2_regime_conditioned_artifacts.py`, `tests/test_reportv2_regimes_optional.py`, `tests/test_reportv2_reality_check_optional.py`, optionally `tests/test_profile_timings_optional.py`; `pyproject.toml` or `pytest.ini` (register mark). |
| **Interfaces affected** | None (test only). |
| **Tests to add/adjust** | No new tests; existing tests get mark. CI/config can run integration separately. |
| **Rollback** | Remove marks and config. |
| **Behavior** | **No behavior change.** Acceptance: default `pytest` still runs all tests; `pytest -m "not integration"` excludes heavy reportv2 runs; `pytest -m integration` runs only marked tests. |

---

### Slice 7: Document and enforce “no OLS outside factors” (doc + optional test)

| Item | Detail |
|------|--------|
| **Scope** | Document in CONTRIBUTING or spec: “OLS and residual betas must be computed via crypto_analyzer.factors (compute_ols_betas, causal_rolling_ols) or alpha_research (signal_residual_momentum_24h with allow_lookahead=False). No reimplementation in CLI scripts.” Add a static or runtime test that fails if scan/analyze/report_daily import and call a local OLS implementation instead of factors/alpha_research. |
| **Files touched** | `docs/spec/components/pipeline_contracts.md` or CONTRIBUTING.md (short subsection); `tests/` (one test that imports cli.scan, cli.analyze, cli.report_daily and asserts they use factors.compute_ols_betas or alpha_research for residual/OLS). |
| **Interfaces affected** | None (documentation and test only). |
| **Tests to add/adjust** | New test: “CLI residual/OLS paths use factors or alpha_research” (import check or call graph). |
| **Rollback** | Remove doc paragraph and test. |
| **Behavior** | **No behavior change.** Acceptance: current behavior unchanged; future PRs that add OLS in CLI fail the new test unless they use factors/alpha_research. |

---

### Slice 8: Walk-forward factor fit per fold (behavior change; optional / defer)

| Item | Detail |
|------|--------|
| **Scope** | In reportv2 walk-forward path, for each fold: build factor matrix and run rolling OLS (or load materialized factor run) using **train window only** for fitting; apply to test window with no data from test. This requires either (a) per-fold factor_run materialization, or (b) in-memory per-fold causal_rolling_ols with train-only lookback. |
| **Files touched** | `cli/research_report_v2.py` (walk-forward loop: pass train index to factor builder; ensure no test data in factor fit); `crypto_analyzer/factors.py` (may need API that accepts explicit time mask or train end index). |
| **Interfaces affected** | Factor build API may need “as_of” or “train_end_ts” to restrict fit to train; reportv2 passes per-fold train boundary. |
| **Tests to add/adjust** | Walk-forward leakage test: assert factor fit uses only train timestamps; add test that fails if full-series fit is used in test window. |
| **Rollback** | Revert to full-series factor build in reportv2. |
| **Behavior** | **Behavior change.** Acceptance: (1) For each fold, factor model is fit only on train timestamps. (2) Signal/validation on test use only those factors. (3) Metrics may change vs current (stricter); document in release notes. |
| **Note** | Mark as **DEFER** if scope is large; can be a follow-on slice after Slices 1–7. |

---

## Stop-the-line risk list (what not to touch)

- **db/migrations.py** — Idempotent CREATE/ALTER semantics; do not change semantics of existing migrations. Add new migrations only when required; do not rename or remove existing tables/columns without a documented migration path.
- **Provider interface method signatures** — `SpotPriceProvider.get_spot(symbol)`, `DexSnapshotProvider.get_snapshot(chain_id, pair_address)`, `search_pairs(query, chain_id)`. Do not change names or signatures (project rule).
- **Config schema keys** — e.g. `db.path`, `providers.spot_priority`, `providers.dex_priority`. Add keys only; do not rename or remove without migration note.
- **Public API surface of data.py** — Function names and return shapes consumed by reports/dashboard (`load_bars`, `load_snapshots`, `get_factor_returns`, `get_research_assets` contract). Extend only; document any breaking change.
- **Experiment registry primary keys and required columns** — experiments, experiment_metrics, experiment_artifacts row shape used by promotion and reportv2. Add columns only; do not drop or rename without migration.
- **ValidationBundle schema** — Dataclass and JSON shape used by promotion gating and reportv2. Add optional fields only; do not remove or change meaning of existing fields.
- **Determinism guarantees** — dataset_id, run_id, stable_run_id, CRYPTO_ANALYZER_DETERMINISTIC_TIME behavior. Do not change hashing or ordering that would break deterministic rerun tests.
- **Default behavior of reportv2** — Default flags (e.g. no --factor-run-id, no --strict-alignment by default) must remain so unless a slice explicitly changes them and documents acceptance criteria.
- **Phase 3 opt-in** — run_migrations_phase3 and ENABLE_REGIMES remain opt-in; do not make phase3 tables or regime features mandatory in default run_migrations.

---

**Files changed (this plan):**  
- Added: `docs/audit/architecture_simplification_plan.md`

**Commands to run:**  
- None (doc-only).

**What to look for:**  
- When implementing slices: run tests after each slice; rollback plan is revert of listed files.
