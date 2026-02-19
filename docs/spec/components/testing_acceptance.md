# Testing and acceptance criteria

**Purpose:** Unit tests by component, integration tests, statistical tests, multiple-testing correction strategy, minimum evidence thresholds, and acceptance criteria.  
**Canonical spec:** [../master_architecture_spec.md](../master_architecture_spec.md)

---

## Unit tests

**Residualizer (leakage + math correctness)**  
- Synthetic dataset where true beta changes over time; rolling OLS must approximate piecewise betas; Kalman beta (if implemented) must track smoothly.  
- "Future leak sentinel": construct returns where future factor returns encode a pattern; assert that as_of_lag_bars>=1 prevents the residualizer from exploiting it (regression should fail to "predict" if causal).  
- Confirm that signal_residual_momentum_24h-style full-sample fitting is rejected or quarantined behind an explicit allow_lookahead=False guard.

**RegimeDetector (causality)**  
- Fit on train, predict on test, assert no use of test timestamps in fitted parameters (store and compare).  
- If probabilities emitted, they must sum to 1.0 ± 1e-6 per timestamp.

**ExecutionCostModel**  
- Deterministic cost application: same inputs → identical outputs and output hash.  
- Stress edges: missing liquidity → fallback slippage cost equals conservative cap (similar to today's slippage_bps() returning 50 bps when liquidity is invalid).

**MultipleTestingAdjuster**  
- BH/BY on known p-value vectors (golden tests).  
- Verify monotonicity of adjusted p-values and correct discovery set at a fixed q.

**Bootstrapper**  
- Reproducibility with fixed seed (seed=42 pattern matches today's bootstrap usage).  
- Stationary bootstrap: mean/variance of resamples approximate original series.

---

## Integration tests

**End-to-end: ingestion → report generation**  
- Use mocked HTTP (your repo already enforces "no live network calls" in tests) and a temp SQLite DB.  
- Run: poll → materialize → reportv2, assert:  
  - bars tables created and non-empty  
  - report and manifest written  
  - experiment registry contains run row + metrics + artifacts

**Deterministic re-run test**  
- Same DB snapshot + same config + same git commit must produce identical:  
  - dataset_id (already deterministic)  
  - report artifact SHA256 (already supported)  
  - run_id if you choose stable hashing for run identity

**Walk-forward leakage test**  
- For each fold, enforce:  
  - factor/regime models fitted only on train timestamps  
  - signals for test timestamps computed without accessing future within test beyond allowed lags  
- This test should fail if any model is fit using the full dataset (exactly the class of bug that "full-sample OLS residual momentum" represents).

---

## Statistical tests

**Null model baseline (mandatory gate)**  
- Null 1: "rank noise" signal (random cross-sectional ranks each timestamp).  
- Null 2: "permuted signal" (cross-sectional permutation each timestamp).  
- Null 3: "block-shuffled time" (block permutation of time buckets) for time-dependent strategies.

**Permutation/placebo tests**  
- Require that any accepted signal beats placebo distributions with corrected inference:  
  - compute IC mean under null distribution  
  - compute p-value as fraction of null ≥ observed  
  - adjust p-values across the tested family

**Multiple testing correction strategy (default)**  
- Default family = all (signal_name × horizon × parameter_grid × regime_variant) tested in a sweep run.  
- Use BH at q=5% as default; BY as conservative option when dependence suspected.

**Minimum evidence threshold to accept a signal (defaults; explicit)**  
A signal is "Accepted" only if all are true (on stitched OOS periods):  
- Mean Spearman IC ≥ **0.02** over ≥ **200** timestamps with ≥ **10** assets each timestamp  
- IC t-stat ≥ **2.5** (computed on IC time series)  
- BH-adjusted p-value ≤ **0.05** (family defined above)  
- Net annualized Sharpe ≥ **1.0** after costs, and lower bound of bootstrap Sharpe CI ≥ **0.0**  
- Deflated Sharpe z-score ≥ **1.0** with n_trials equal to the tested family size (not a hand-waved constant)
