# Drift register

Spec mismatches, “spec incomplete,” and “implementation stronger than spec.” For each: severity, risk, recommended action. No code changed.

---

## Spec mismatch (implementation differs from spec)

| ID | Item | Severity | Risk | Recommended action |
|----|------|----------|------|--------------------|
| D1 | **Pipeline contract: Ingestion “chain”** — Spec describes SpotPriceChain / DexSnapshotChain with resilience; poll is script-style with direct fetch + insert. Provider registry and resilience exist in `crypto_analyzer/providers/` but not as a single “chain” call from poll. | Low | Low. Behavior matches (providers, retry, LKG). | [DOC ONLY] Update pipeline_contracts to say “provider chain pattern implemented via registry + resilience; poll orchestrates fetches and writes.” |
| D2 | **Factor model: reportv2 path** — Spec says factor outputs can be materialized (factor_model_runs, factor_betas, residual_returns). reportv2 builds factors in-memory via build_factor_matrix + rolling_multifactor_ols and does not use materialized factor_run_id by default. | Medium | Cache/repro benefits of factor_materialize not used in main report path. | [DOC ONLY] Document; optionally add “use materialized factor run” to reportv2. [SAFE REFACTOR] |
| D3 | **Integrity: hard-block** — Spec says “fail fast or warn loudly” on alignment; integrity.py mostly warns. reportv2 uses assert_* but many paths do not exit non-zero. | Low | Misaligned indices could produce silent NaNs. | [BEHAVIOR CHANGE] Define which checks are hard-block; implement in integrity.py + reportv2. |
| D4 | **Versioning: engine_version, config_version** — versioning_release says add engine_version and config_version to experiments and manifest. implementation_ledger marks “Not started.” Code has config_hash, spec_version, git_commit but not engine_version/config_version. | Low | Harder to reproduce exact engine/config across runs. | [SAFE REFACTOR] Add columns and manifest fields; set in record_experiment_run and make_run_manifest. |
| D5 | **research_report.py residual signal** — Calls signal_residual_momentum_24h(returns_df, args.freq) without explicit allow_lookahead. Default is False (causal), but spec and risk_audit stress explicit guard. | Low | No current leak; clarity and future-proofing. | [SAFE REFACTOR] Add allow_lookahead=False explicitly in cli/research_report.py. |
| D6 | **Walk-forward factor fit** — Spec says factor fitting must be restricted to available history per fold. reportv2 walk-forward uses same full-series rolling OLS for signals; it does not re-fit factors per train fold. | Medium | Theoretically allows information from “future” bars within the full series when computing betas for test window. | [DOC ONLY] Document in pipeline_contracts / risk_audit; consider per-fold factor fit in future. [DEFER] |

---

## Spec incomplete (spec does not describe what exists)

| ID | Item | Severity | Risk | Recommended action |
|----|------|----------|------|--------------------|
| I1 | **ValidationBundle** — Per-signal bundle (IC series, decay, turnover, paths) and JSON emission are implemented (validation_bundle.py, reportv2) but not fully described in pipeline_contracts / research_repo_mapping. | Low | None. | [DOC ONLY] Add ValidationBundle to pipeline_contracts “Signal validation” and “Reporting” outputs. |
| I2 | **ExecutionCostModel** — Unified execution_cost.py (fee, slippage, spread proxy, participation impact) and apply_costs_to_portfolio delegation are in place; interfaces.md describes ExecutionCostModel but pipeline_contracts and risk_audit do not list optional spread_vol_scale / participation. | Low | None. | [DOC ONLY] Extend pipeline_contracts “Execution realism” and risk_audit to mention execution_cost.py and optional params. |
| I3 | **Phase 3 schema** — regime_runs, regime_states, promotion_candidates, promotion_events, sweep_families, sweep_hypotheses live in migrations_phase3.py; schema_plan and master spec mention them but core run_migrations does not apply phase3 (opt-in). | Low | Confusion about which DBs have which tables. | [DOC ONLY] State in schema_plan that phase3 tables are opt-in via run_migrations_phase3 and env flag. |
| I4 | **Caches** — factor_cache, regime_cache, rc_cache (stats/) are implemented; performance_scale describes caching plan but not these concrete modules. | Low | None. | [DOC ONLY] Add cache module names and keys to performance_scale.md. |
| I5 | **Promotion workflow** — store_sqlite, service, gating, execution_evidence, CLI promotion list/create/evaluate, Streamlit Promotion page exist; phased_execution lists them but master spec “Reporting” does not detail promotion. | Low | None. | [DOC ONLY] Add “Promotion (candidate → accepted)” to Reporting section and dependency graph. |
| I6 | **Null suite** — null_suite runner and CLI exist; testing_acceptance describes null baselines but does not reference crypto_analyzer/null_suite.py and scripts/run.ps1 null_suite. | Low | None. | [DOC ONLY] Reference null_suite in testing_acceptance.md. |
| I7 | **Romano–Wolf** — Implemented (opt-in via CRYPTO_ANALYZER_ENABLE_ROMANOWOLF=1); outputs rw_adjusted_p_values when enabled. interfaces and implementation_ledger updated. | Low | None. | [DONE] implementation_ledger and interfaces.md now state RW implemented, opt-in; see methods_and_limits.md §9. |
| I8 | **Determinism env** — CRYPTO_ANALYZER_DETERMINISTIC_TIME used in reportv2 deterministic rerun and factor materialize; not documented in versioning_release or governance. | Low | Reproducibility may be missed by users. | [DOC ONLY] Document in versioning_release or README. |

---

## Implementation stronger than spec

| ID | Item | Severity | Risk | Recommended action |
|----|------|----------|------|--------------------|
| S1 | **Residual signal leakage fix** — allow_lookahead=False default and quarantined lookahead path; leakage sentinel test. Spec required it; implementation delivers. | — | None. | [DOC ONLY] Mark in implementation_ledger as Done; reference test_leakage_sentinel. |
| S2 | **ValidationBundle contract** — Dataclass and per-signal emission with artifact paths; reportv2 writes bundle JSON + IC/decay/turnover CSVs. | — | None. | [DOC ONLY] Align spec “validation bundle” with validation_bundle.py and reportv2. |
| S3 | **Unified ExecutionCostModel** — execution_cost.py with apply_costs, slippage_bps_from_liquidity, spread_bps_from_vol_liquidity, capacity curve; portfolio and backtest delegate. | — | None. | [DOC ONLY] Confirm in spec that ExecutionCostModel is the single cost path. |
| S4 | **BH/BY MultipleTestingAdjuster** — multiple_testing_adjuster.py; reportv2 stores adjusted p-values; family from signals in run. | — | None. | [DOC ONLY] implementation_ledger: Done; wire into acceptance criteria doc. |
| S5 | **Stationary bootstrap** — statistics.py method=stationary; bootstrap_method and seed in artifacts. | — | None. | [DOC ONLY] implementation_ledger: Done. |
| S6 | **Null suite runner** — null_suite.py + CLI; null_ic_dist, null_sharpe_dist, null_pvalues; deterministic with seed. | — | None. | [DOC ONLY] implementation_ledger: Done; testing_acceptance: reference. |
| S7 | **Spread + participation impact** — execution_cost spread proxy and participation-based impact; capacity curve. | — | None. | [DOC ONLY] Spec “execution realism” already aligned; note optional params. |
| S8 | **Schema migrations v2 + phase3** — migrations_v2.py (versioned, backup/restore); migrations_phase3.py (regime_*, promotion_*, sweep_*). | — | None. | [DOC ONLY] implementation_ledger: Done; schema_plan: clarify v2 vs phase3. |
| S9 | **RegimeDetector** — fit/predict, filter-only in test, smooth raises; regime_materialize with run_id. | — | None. | [DOC ONLY] interfaces + implementation_ledger: Done. |
| S10 | **Regime-conditioned validation** — ic_summary_by_regime, ic_decay_by_regime, regime_coverage; ValidationBundle meta/paths; exact join; no leakage. | — | None. | [DOC ONLY] implementation_ledger: Done. |
| S11 | **Kalman/RLS dynamic beta** — factors_dynamic_beta.py; factor_materialize supports kalman_beta; as_of_lag_bars>=1. | — | None. | [DOC ONLY] implementation_ledger: Done. |
| S12 | **Reality Check** — stats/reality_check.py; family_id; reportv2 --reality-check; RC persist to sweep tables when phase3. | — | None. | [DOC ONLY] implementation_ledger: Done. |
| S13 | **Promotion workflow** — promotion store, service, gating, execution_evidence, CLI, Streamlit; RC and execution evidence gates. | — | None. | [DOC ONLY] implementation_ledger: Done. |
| S14 | **Factor/regime/RC caches** — factor_cache, regime_cache, rc_cache; --no-cache and CRYPTO_ANALYZER_NO_CACHE. | — | None. | [DOC ONLY] performance_scale: add these. |
| S15 | **Deterministic rerun test** — test_reportv2_deterministic_rerun with CRYPTO_ANALYZER_DETERMINISTIC_TIME; byte-identical bundle and manifest. | — | None. | [DOC ONLY] testing_acceptance: reference. |

---

**Files changed (this audit):**  
- Added: `docs/audit/drift_register.md`

**Commands to run:**  
- None (read-only).

**What to look for:**  
- Use drift IDs (D*, I*, S*) when updating spec or implementation_ledger; prioritize D2, D6 for behavior/docs.
