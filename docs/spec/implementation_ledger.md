# Implementation Ledger

**Purpose:** Track spec requirements to implementation status, PRs, and evidence. Canonical spec: [master_architecture_spec.md](master_architecture_spec.md).

## How to use this ledger

- **Spec requirement**: Short label from the master spec or component file/section.
- **Component file/section**: Where the requirement is defined (for traceability).
- **Implementation status**: Not started | In progress | Done | Blocked.
- **PR link**: URL or PR number once implemented.
- **Files changed**: Key modules/files touched.
- **Tests**: Unit / integration / statistical tests added or updated.
- **Evidence/hashes**: Artifact hashes, dataset_id, or run IDs that prove the behavior.
- **Notes**: Caveats, follow-ups, or dependencies.

Update rows as work completes. Keep the master spec unchanged; extend component specs only when the spec itself evolves.

---

## Requirement table

| Spec requirement | Component file/section | Implementation status | PR link | Files changed | Tests | Evidence/hashes | Notes |
|------------------|------------------------|------------------------|---------|---------------|-------|-----------------|-------|
| Research mechanism specs (Report A & B: goal, inputs, outputs, assumptions, validation, failure modes) | [research_mechanisms.md](components/research_mechanisms.md) | Not started | | | | | |
| Pipeline contract: Ingestion → Reporting (inputs, outputs, invariants, error handling per stage) | [pipeline_contracts.md](components/pipeline_contracts.md) | Not started | | | | | |
| Baseline + refined dependency graph (Mermaid) | [dependency_graph.md](components/dependency_graph.md) | Not started | | | | | |
| Research ↔ repo mapping table (mechanism → stage, status, changes, interfaces, tests, acceptance) | [research_repo_mapping.md](components/research_repo_mapping.md) | Not started | | | | | |
| Schema evolution: schema_migrations, factor_model_runs, factor_betas, residual_returns, regime_* | [schema_plan.md](components/schema_plan.md) | Not started | | | | | |
| Migration strategy: versioned runner, backward compatibility, rollback | [schema_plan.md](components/schema_plan.md) | Not started | | | | | |
| Interface: Residualizer (as_of_lag_bars, leakage hardening) | [interfaces.md](components/interfaces.md) | Not started | | | | | |
| Interface: RegimeDetector (fit/predict, filter-only in test) | [interfaces.md](components/interfaces.md) | Not started | | | | | |
| Interface: ExecutionCostModel (unified spread/impact) | [interfaces.md](components/interfaces.md) | Not started | | | | | |
| Interface: MultipleTestingAdjuster (BH/BY) | [interfaces.md](components/interfaces.md) | Not started | | | | | |
| Interface: Bootstrapper (block + stationary, seed) | [interfaces.md](components/interfaces.md) | Not started | | | | | |
| Unit tests: Residualizer, RegimeDetector, ExecutionCostModel, MultipleTestingAdjuster, Bootstrapper | [testing_acceptance.md](components/testing_acceptance.md) | Not started | | | | | |
| Integration tests: ingestion→report, deterministic rerun, walk-forward leakage | [testing_acceptance.md](components/testing_acceptance.md) | Not started | | | | | |
| Statistical tests: null suite, permutation/placebo, multiple-testing correction, acceptance thresholds | [testing_acceptance.md](components/testing_acceptance.md) | Not started | | | | | |
| Versioning: SemVer rules, config_version, model artifact versioning, repro metadata in DB | [versioning_release.md](components/versioning_release.md) | Not started | | | | | |
| Performance: hotspots, runtime expectations, caching plan, SQLite limits + migration path | [performance_scale.md](components/performance_scale.md) | Not started | | | | | |
| Risk audit: leakage vectors, overfitting, regime dependence, capacity illusions, what NOT to implement | [risk_audit.md](components/risk_audit.md) | Not started | | | | | |
| Phase 1: Patch leakage (causal residualizer, as_of_lag_bars; quarantine lookahead) | [phased_execution.md](components/phased_execution.md), [master_architecture_spec.md](master_architecture_spec.md) | Done | *(PR link)* | crypto_analyzer/factors.py, crypto_analyzer/alpha_research.py | tests/test_leakage_sentinel.py | Leakage sentinel: causal path no abnormal IC; allow_lookahead=False default | |
| Phase 1: ValidationBundle contract + reportv2 emit per signal | [phased_execution.md](components/phased_execution.md) | Done | *(PR link)* | crypto_analyzer/validation_bundle.py, cli/research_report_v2.py | run.ps1 verify | Per-signal bundle JSON + IC/decay/turnover CSVs (relative paths) | |
| Phase 1: Deterministic rerun integration test | [phased_execution.md](components/phased_execution.md) | Done | *(PR link)* | tests/test_reportv2_deterministic_rerun.py, crypto_analyzer/timeutils.py, crypto_analyzer/artifacts.py, crypto_analyzer/governance.py | run.ps1 verify | test_deterministic_rerun_identical_bundle_and_manifest; env CRYPTO_ANALYZER_DETERMINISTIC_TIME | |
| Phase 1: Unify cost model (ExecutionCostModel) | [phased_execution.md](components/phased_execution.md) | Done | *(PR link)* | crypto_analyzer/execution_cost.py, crypto_analyzer/portfolio.py, cli/backtest.py | tests/test_execution_cost.py, run.ps1 verify | Same inputs → identical net_returns; higher turnover → higher costs; missing liquidity fallback | |
| Phase 2: schema_migrations + versioned migration runner (backup/restore) | [schema_plan.md](components/schema_plan.md), [phased_execution.md](components/phased_execution.md) | Done | *(PR link)* | crypto_analyzer/db/migrations_v2.py, crypto_analyzer/db/migrations.py, ingest/__init__.py, read_api.py | test_migrations_v2_on_empty_db_creates_tables_and_records, test_migrations_v2_rerun_idempotent, test_migrations_v2_in_memory_no_backup, test_migrations_v2_failure_restores_backup | run_migrations(conn, db_path) from ingest/read_api; backup = copy on-disk DB, restore on failure; failure test asserts schema_migrations + factor_model_runs row count unchanged | No backup when db_path=None (log); idempotent CREATE INDEX IF NOT EXISTS |
| Phase 2: factor_model_runs, factor_betas, residual_returns + materialize path | [schema_plan.md](components/schema_plan.md) | Done | *(PR link)* | crypto_analyzer/factor_materialize.py, crypto_analyzer/factors.py (causal_rolling_ols) | test_factor_run_id_deterministic, test_materialize_factor_run_writes_tables, test_materialize_deterministic_under_fixed_time, test_materialize_idempotent_same_run_id, test_as_of_lag_bars_must_be_at_least_one, test_causal_residuals_no_future_data | factor_run_id = hash(canonical JSON + dataset_id); CRYPTO_ANALYZER_DETERMINISTIC_TIME → same row counts and ordered content; as_of_lag_bars>=1 enforced in causal_rolling_ols | Determinism: env CRYPTO_ANALYZER_DETERMINISTIC_TIME for reproducible materialize |
| Phase 2: MultipleTestingAdjuster (BH/BY) + registry (adjusted p-values, family) | [interfaces.md](components/interfaces.md), [research_repo_mapping.md](components/research_repo_mapping.md) | Done | *(PR link)* | crypto_analyzer/multiple_testing_adjuster.py, cli/research_report_v2.py | test_bh_golden, test_by_more_conservative_than_bh, test_adjust_monotonicity, test_adjust_reproducible, test_no_family_empty_unchanged, test_no_family_nan_handling | reportv2: p_value_raw_<s>, p_value_adj_bh_<s>, p_value_family_adjusted (method bh in naming); family = signals in run (deterministic); no double-adjust on rerun | Explicit family_id = hash(config+signals+horizons+grid) recommended follow-up |
| Phase 2: Stationary bootstrap option + method/seed in artifacts | [interfaces.md](components/interfaces.md) | Done | *(PR link)* | crypto_analyzer/statistics.py | tests/test_statistics_research.py | method=stationary, seed → reproducible; significance_summary returns bootstrap_method, bootstrap_seed, block_length | |
| Phase 2: Null suite runner (random ranks, permuted signal, block shuffle) | [testing_acceptance.md](components/testing_acceptance.md) | Done | *(PR link)* | crypto_analyzer/null_suite.py, cli/null_suite.py, scripts/run.ps1 | test_null_suite_produces_artifacts, test_null_1_deterministic, test_null_2_permutes_per_row, test_null_3_block_shuffle_reorders_rows | CLI: .\scripts\run.ps1 null_suite; artifacts: null_ic_dist.csv, null_sharpe_dist.csv, null_pvalues.json; fixed seed → deterministic output | Nulls built without future returns; block shuffle preserves within-block dependence |
| Phase 2: Spread proxy + participation impact + capacity curve | [phased_execution.md](components/phased_execution.md) | Done | *(PR link)* | crypto_analyzer/execution_cost.py | test_spread_increases_with_vol_and_lower_liquidity, test_impact_increases_with_participation, test_capacity_curve_multipliers, test_same_inputs_identical_net_returns, test_missing_liquidity_conservative_fallback | spread_vol_scale=0, use_participation_impact=False default (opt-in); capacity_curve fixed fee/slippage, varies notional multiplier only | Monotonicity: lower liq/higher vol → higher spread; higher participation → higher impact |
| Phase 2: E2E integration (migrations → materialize → registry → null suite) | [phased_execution.md](components/phased_execution.md) | Done | *(PR link)* | tests/test_phase2_integration.py | test_phase2_e2e_migrations_factor_registry_null_artifacts | Temp DB → run_migrations(conn, db_path) → materialize_factor_run → record_experiment_run → run_null_suite → write_null_suite_artifacts | Contract frozen in phase2_pr_description.md |
| Phase 3 checklist: regime models, Kalman beta, sweep registry, performance optimization, promotion workflow | [phased_execution.md](components/phased_execution.md) | Not started | | | | | |

---

## Decisions log

| Date | Decision | Rationale |
|------|----------|-----------|
| *(placeholder)* | *(e.g. Adopt BH at q=5% as default family-wide)* | *(optional)* |
| *(placeholder)* | | |
