# Phased execution checklist

**Purpose:** Phase 1/2/3 checkbox execution checklist for implementing the research upgrades.
**Canonical spec:** [../master_architecture_spec.md](../master_architecture_spec.md)

Canonical status: implementation_ledger and drift_register (S1–S15) record completed items.

---

## Phased execution checklist

### Phase 1 (1–3 days)

- [x] Patch leakage: replace/disable full-sample signal_residual_momentum_24h with a rolling or fold-causal residualizer (enforce as_of_lag_bars).
- [x] Create ValidationBundle contract (dataclass) and refactor reportv2 to emit it for each signal (IC series, t-stat, decay, turnover, lead/lag).
- [x] Add integration test: deterministic rerun hash equality (manifest + artifact SHA).
- [x] Unify cost model: move slippage logic from cli/backtest.py and bps cost logic from portfolio.py into one ExecutionCostModel with a single config path.

### Phase 2 (1–2 weeks)

- [x] Implement schema_migrations + versioned migration runner; add tables: factor_model_runs, factor_betas, residual_returns.
- [x] Implement BH FDR correction (MultipleTestingAdjuster) and wire into sweep runner + experiment registry metrics (store adjusted p-values).
- [x] Add stationary bootstrap option to Bootstrapper; update stats corrections outputs to record bootstrap method + seed.
- [x] Add a "null suite" runner: random signal, permuted cross-section, block-shuffled time; require reports to show null results next to real signals.
- [x] Implement basic spread model (vol/liquidity proxy) + size-dependent impact (participation proxy) and generate capacity-vs-performance curves.

### Phase 3 (1–2 months)

- [x] Add statistically anchored regime models with causal filtering (ARCH/GARCH volatility regime OR Markov switching), persisted as regime_runs / regime_states. *(Slice 1: threshold-vol regime + regime_features + RegimeDetector filter-only; migrations in migrations_phase3.py; reportv2 --regimes optional.)*
- [x] Regime-conditioned validation outputs + promotion gating hooks (interfaces only). *(Slice 2: ic_summary_by_regime, ic_decay_by_regime, regime_coverage artifacts; exact join; ValidationBundle meta/paths; ThresholdConfig + evaluate_candidate; require_regime_robustness=False default.)*
- [x] Add dynamic beta estimator (Kalman) as optional factor model estimator; compare OOS factor exposure removal vs rolling OLS baseline. *(Slice 3: kalman_beta in FactorMaterializeConfig; dynamic_beta_rls in factors_dynamic_beta.py; same schema; as_of_lag_bars>=1.)*
- [x] Dependence-aware data-snooping correction (Reality Check); Romano–Wolf (implemented, opt-in). *(Slice 4: family_id, stats/reality_check.py, reportv2 --reality-check opt-in; promotion require_reality_check; RW maxT stepdown when CRYPTO_ANALYZER_ENABLE_ROMANOWOLF=1, outputs rw_adjusted_p_values.)*
- [x] Sweep registry hardening: persist sweep families + hypothesis ids; enforce corrected inference gates in promotion by default for sweeps (RC required; BH/BY allowed for exploratory only).
- [x] Execution realism gates: define "capacity-aware acceptance" (min liquidity, max participation, spread/impact config) and store it as part of promotion evidence; fail promotion if missing.
- [x] Performance optimization (measured): add factor/regime cache keyed by (dataset_id, config_hash, git_commit); profile materialization loops; accelerate only after correctness gates pass. *(RC null cache already implemented in Slice 5.)*
- [x] Add an explicit "research promotion workflow" in the UI: exploratory → candidate → accepted, based on the acceptance criteria and stored evidence artifacts. *(Slice 5: promotion_candidates/promotion_events, store_sqlite + service, Streamlit Promotion page, CLI promotion list/create/evaluate; RC null cache + manifest; opt-in, no default change.)*
