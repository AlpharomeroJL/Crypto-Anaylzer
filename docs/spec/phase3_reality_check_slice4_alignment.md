# Phase 3 Slice 4: Reality Check / Romano–Wolf (dependence-aware data-snooping correction) — alignment

**Canonical spec:** [master_architecture_spec.md](master_architecture_spec.md), [testing_acceptance.md](components/testing_acceptance.md), [risk_audit.md](components/risk_audit.md), [research_repo_mapping.md](components/research_repo_mapping.md), [interfaces.md](components/interfaces.md), [phased_execution.md](components/phased_execution.md).

## Metric used for correction

- **Default metric:** `mean_ic` (mean Spearman IC over time for one hypothesis).
- **Rationale:** Aligns with existing validation (IC summary, t-stat, BH-adjusted p-value); one number per (signal, horizon); no extra portfolio run.
- **Alternative:** `deflated_sharpe` (net portfolio Sharpe of the strategy). Supported via config; requires portfolio PnL per hypothesis.
- **Horizon:** When metric = `mean_ic`, a single `horizon` (e.g. 1) is required so hypothesis = (signal, horizon) is well-defined.

## Family definition and family_id

- **Family:** Set of hypotheses = signals × horizons × (optional params/estimator/regime). For reportv2 minimal slice: signals × horizons (one estimator, one regime run or none).
- **family_id:** Stable hash from canonical payload: config_hash, sorted(signals), sorted(horizons), estimator, params_grid_id (hash of sorted params if any), regime_run_id (or ""). No timestamps. Keys sorted; lists sorted. Same style as factor_run_id / dataset_id (e.g. `rcfam_` + 16 hex).
- **Hypothesis id (hypothesis_id):** Deterministic string per hypothesis, e.g. `signal|horizon` or `signal|horizon|params|estimator|regime`. Used to index observed_stats and null matrix columns; stable ordering (sorted).

## RC algorithm

- **Observed:** T_obs = max over hypotheses h of observed_stats[h].
- **Null:** For each simulation b = 0..B-1, null_generator(b) returns a vector of null statistics (one per hypothesis). T_b = max over h of null_b[h].
- **p-value:** RC p-value = (1 + #{b : T_b >= T_obs}) / (B + 1).
- **Joint null:** The same resampling (e.g. one block draw per b) is used for all hypotheses so dependence is preserved.

## RW algorithm (Romano–Wolf stepdown)

- **Slice 4:** Implement RC only; RW stepdown is stubbed with clear TODO and gated by CRYPTO_ANALYZER_ENABLE_ROMANOWOLF=1 (raises NotImplementedError or returns empty until implemented).
- **Intended (deferred):** Order hypotheses by observed stat descending; stepdown adjusted p-value for hypothesis j = max over bootstrap of (indicator that max over remaining set >= observed_j); deterministic.

## Null generation

- **Method:** `stationary` (Politis–Romano, geometric block lengths) or `block_fixed` (fixed block size). Reuse `crypto_analyzer.statistics._stationary_bootstrap_indices` and same pattern for block_fixed.
- **Parameters:** `avg_block_length` (stationary) or block size; `seed` for determinism.
- **Contract:** Null generator receives per-hypothesis time series (e.g. IC series); for each b it draws one resample index vector (same length as series), then for each hypothesis computes the statistic (e.g. mean) on the resampled series. Same indices across hypotheses so dependence is preserved. No future data: resampling is over observed time only.

## Persistence

- **Registry metric keys:** `family_id`, `rc_p_value`, `rc_metric`, `rc_horizon`, `rc_n_sim`, `rc_seed`, `rc_method`, `rc_avg_block_length`, `rc_observed_max`. Optional later: `rw_min_adjusted_pvalue`, etc.
- **Artifact filenames:** `reality_check_summary_{family_id}.json`, `reality_check_null_max_{family_id}.csv` (one column null_max per row = bootstrap draw). Optional: `romanowolf_adjusted_pvalues_{family_id}.csv` (stub).
- **Summary JSON schema:** family_id, rc_p_value, observed_max, metric, horizon, n_sim, seed, method, avg_block_length, hypothesis_ids (list), observed_stats (dict or list).

## Test plan and acceptance

- **Determinism:** Same observed_stats + seed + n_sim => identical rc_p_value and null_max distribution (hash or first few moments).
- **Null sanity:** Under pure null (e.g. random observed stats from null distribution), RC p-value should not be degenerate at 0 (smoke: mean p-value over many runs > 0.05 or similar).
- **Edge detection (smoke):** Inject one hypothesis with true edge; RC p-value should be small (e.g. < 0.10) in most runs.
- **Integration:** reportv2 without --reality-check unchanged; with --reality-check writes artifacts and registry metrics; deterministic under CRYPTO_ANALYZER_DETERMINISTIC_TIME.
- **CI:** Use small n_sim (e.g. 50–200) in tests so runtime is bounded.

## Promotion gating (Slice 2 extension)

- **ThresholdConfig:** `require_reality_check: bool = False`, `max_rc_p_value: float = 0.05`. When True, reject unless rc_p_value <= max_rc_p_value (from bundle meta or provided rc_summary). Default OFF.
