# Phased execution checklist

**Purpose:** Phase 1/2/3 checkbox execution checklist for implementing the research upgrades.  
**Canonical spec:** [../master_architecture_spec.md](../master_architecture_spec.md)

---

## Phased execution checklist

### Phase 1 (1–3 days)

- [x] Patch leakage: replace/disable full-sample signal_residual_momentum_24h with a rolling or fold-causal residualizer (enforce as_of_lag_bars).
- [x] Create ValidationBundle contract (dataclass) and refactor reportv2 to emit it for each signal (IC series, t-stat, decay, turnover, lead/lag).
- [x] Add integration test: deterministic rerun hash equality (manifest + artifact SHA).
- [x] Unify cost model: move slippage logic from cli/backtest.py and bps cost logic from portfolio.py into one ExecutionCostModel with a single config path.

### Phase 2 (1–2 weeks)

- [ ] Implement schema_migrations + versioned migration runner; add tables: factor_model_runs, factor_betas, residual_returns.
- [ ] Implement BH FDR correction (MultipleTestingAdjuster) and wire into sweep runner + experiment registry metrics (store adjusted p-values).
- [ ] Add stationary bootstrap option to Bootstrapper; update stats corrections outputs to record bootstrap method + seed.
- [ ] Add a "null suite" runner: random signal, permuted cross-section, block-shuffled time; require reports to show null results next to real signals.
- [ ] Implement basic spread model (vol/liquidity proxy) + size-dependent impact (participation proxy) and generate capacity-vs-performance curves.

### Phase 3 (1–2 months)

- [ ] Add statistically anchored regime models with causal filtering (ARCH/GARCH volatility regime OR Markov switching), persisted as regime_runs / regime_states.
- [ ] Add dynamic beta estimator (Kalman) as optional factor model estimator; compare OOS factor exposure removal vs rolling OLS baseline.
- [ ] Build full parameter sweep registry: define "test families," compute corrected inference, and adopt promotion criteria that require survival after correction + execution realism + regime robustness.
- [ ] Performance optimization: cache factor/regime outputs by dataset_id and config hash; profile rolling OLS loops; vectorize or accelerate (Numba or incremental regression) once correctness gates pass.
- [ ] Add an explicit "research promotion workflow" in the UI: exploratory → candidate → accepted, based on the acceptance criteria and stored evidence artifacts.
