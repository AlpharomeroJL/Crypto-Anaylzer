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
| Phase 2 checklist: schema migrations, BH FDR, stationary bootstrap, null suite, spread/impact | [phased_execution.md](components/phased_execution.md) | Not started | | | | | |
| Phase 3 checklist: regime models, Kalman beta, sweep registry, performance optimization, promotion workflow | [phased_execution.md](components/phased_execution.md) | Not started | | | | | |

---

## Decisions log

| Date | Decision | Rationale |
|------|----------|-----------|
| *(placeholder)* | *(e.g. Adopt BH at q=5% as default family-wide)* | *(optional)* |
| *(placeholder)* | | |
