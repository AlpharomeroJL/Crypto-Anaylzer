# Methods & stats implementation alignment audit

This document records the alignment between the stats/methods docs and the repository implementation (docs-only audit; no code changes). It serves as the single reference for method → code location, artifact keys, and known deviations.

## Method | Reference | Implementation location | Artifact keys | Deviations / notes

| Method / area | Canonical reference | Implementation location | Artifact keys | Deviations / notes |
|---------------|---------------------|-------------------------|---------------|--------------------|
| **dataset_id_v2** | docs/methods_and_limits.md §13, README | `crypto_analyzer/dataset_v2.py`::`compute_dataset_id_v2`, `get_dataset_id_v2` | N/A (DB/metadata) | Allowlist: `DATASET_HASH_SCOPE_V2` (spot_price_snapshots, sol_monitor_snapshots, bars_*, universe_allowlist). Ordering: pk, deterministic_keys, ts_then_rowid, rowid_fallback. Mode STRICT/FAST_DEV; promotion requires STRICT. |
| **run_key / run_instance_id** | README, promotion/gating | `crypto_analyzer/core/run_identity.py`::`compute_run_key`, `build_run_identity` | In eligibility reports, bundle meta: run_key, run_instance_id | run_key = hash of semantic payload (excludes timestamps/paths); run_instance_id = execution id (e.g. manifest run_id). |
| **seed_root** | rng.py, schema_versions | `crypto_analyzer/rng.py`::`seed_root(run_key, salt, fold_id=None, version=SEED_ROOT_VERSION)` | seed_version, seed_root in RC summary, fold attestation, bundle meta | fold_id optional; normalized as "fold:{id}" when present. SEED_ROOT_VERSION = 1. |
| **RC/RW provenance** | methods_and_limits §9, §13 | `crypto_analyzer/stats/reality_check.py`::`run_reality_check`, `_romano_wolf_stepdown` | rc_summary: seed_root, component_salt, null_construction_spec, requested_n_sim, actual_n_sim, n_sim_shortfall_warning; rw_adjusted_p_values when RW enabled | component_salt = SALT_RC_NULL when run_key; null_construction_spec has method, avg_block_length, block_size, seed_derivation, seed_version. Gatekeeper blocks if actual_n_sim < 0.95 * requested_n_sim. |
| **Schema versions** | contracts, gating | `crypto_analyzer/contracts/schema_versions.py` (VALIDATION_BUNDLE=1, RC_SUMMARY=1, CALIBRATION=1, SEED_DERIVATION=1); `crypto_analyzer/fold_causality/attestation.py` (FOLD_CAUSALITY_ATTESTATION=1) | validation_bundle_schema_version, rc_summary_schema_version, fold_causality_attestation_schema_version | Gatekeeper requires exact version match. |
| **Fold-causality attestation** | README, gating | `crypto_analyzer/fold_causality/attestation.py`::`build_fold_causality_attestation`, `validate_attestation` | fold_causality_attestation_schema_version, run_key, dataset_id_v2, split_plan_summary, transforms, enforcement_checks, seed_version | checks: train_only_fit_enforced, purge_applied, embargo_applied, no_future_rows_in_fit. |
| **Deflated Sharpe (DSR)** | Bailey & López de Prado (2014); methods_limits_implementation §A | `crypto_analyzer/multiple_testing.py`::`deflated_sharpe_ratio` | raw_sr, deflated_sr (function returns); stats_overview: n_trials_used, n_trials_user, n_trials_eff_eigen, n_trials_eff_inputs_* | Var(SR) uses excess kurtosis (pandas kurtosis()); E[max] ≈ σ_SR √(2 ln N). No μ_SR term (null mean 0). |
| **Neff (effective trials)** | methods_and_limits §7 | `crypto_analyzer/multiple_testing.py`::`effective_trials_eigen(C)` | n_trials_user, n_trials_eff_eigen, n_trials_used, n_trials_eff_inputs_total, n_trials_eff_inputs_used | Neff = (∑λ_i)² / ∑λ_i²; eigenvalues from correlation matrix; ev = max(ev, 0). |
| **BH / BY** | Benjamini–Hochberg (1995), Benjamini–Yekutieli (2001); methods_limits_implementation §B | `crypto_analyzer/multiple_testing_adjuster.py`::`adjust` | Adjusted p-values and discoveries (in-report); no dedicated artifact key list | BH: adj = min(1, p*n/rank); BY: c_n = ∑(1/j), adj = min(1, p*n*c_n/rank). NaNs dropped; monotonicity enforced. |
| **Stationary bootstrap** | Politis & Romano (1994); methods_limits_implementation §D | `crypto_analyzer/statistics.py`::`_stationary_bootstrap_indices` | rc_avg_block_length, bootstrap params in RC summary | p = 1/avg_block_length; L ~ Geometric(p); start uniform in [0, length); wrap mod length. |
| **Reality Check** | White (2000); methods_limits_implementation §E | `crypto_analyzer/stats/reality_check.py`::`run_reality_check`, `reality_check_pvalue` | rc_p_value, observed_max, n_sim, hypothesis_ids, rc_metric, rc_method, rc_avg_block_length, null_construction_spec | Observed = max over hypotheses; null same indices across hypotheses. p = (1 + #{T* ≥ T_obs}) / (B+1). |
| **Romano–Wolf** | Romano & Wolf (2005); methods_limits_implementation §E.3 | `crypto_analyzer/stats/reality_check.py`::`_romano_wolf_stepdown` | rw_adjusted_p_values (when CRYPTO_ANALYZER_ENABLE_ROMANOWOLF=1), rw_enabled in stats_overview | Order: decreasing observed stat. Max-null per step; (1+count)/(B+1); monotonicity enforced. NaN/inf in observed → empty RW output. |
| **CSCV PBO** | Bailey et al. (2014); methods_limits_implementation §H | `crypto_analyzer/multiple_testing.py`::`pbo_cscv` | pbo_cscv, pbo_cscv_blocks, pbo_cscv_total_splits, pbo_cscv_splits_used, pbo_metric; when skipped: pbo_cscv_skipped_reason | **Potential correctness risk:** Splits are random permutations (no full enumeration). May increase variance of PBO estimate vs full enumeration. See Known deviations below. |
| **PBO proxy** | methods_limits_implementation §C | `crypto_analyzer/multiple_testing.py` (walk-forward median-underperformance heuristic) | In overfitting section; not same as pbo_cscv | Per-split “selected” vs median test metric; screening heuristic only. |
| **HAC mean inference** | Newey–West; methods_limits_implementation §G | `crypto_analyzer/statistics.py`::`hac_mean_inference`, `newey_west_lrv` | hac_lags_used, t_hac_mean_return, p_hac_mean_return (report maps t_hac/p_hac), hac_skipped_reason | L = floor(4*(n/100)^(2/9)) capped n/3; min_obs=30. Bartlett weights. |
| **Structural breaks** | methods_and_limits §11 | `crypto_analyzer/structural_breaks.py`::`cusum_mean_shift`, `sup_chow_single_break`, `run_break_diagnostics` | break_diagnostics.json: series → { name: [cusum_entry, scan_entry] }; per entry: series_name, test_name, stat, p_value, break_suspected, estimated_break_*, calibration_method, skipped_reason | CUSUM min_obs=20; scan min_obs=100. |
| **Capacity curve** | methods_and_limits §12 | `crypto_analyzer/execution_cost.py`::`capacity_curve`, `capacity_curve_is_non_monotone`, `impact_bps_from_participation` | capacity_curve_written, non_monotone_capacity_curve_observed; CSV: notional_multiplier, sharpe_annual; execution_evidence: cost_config, capacity_curve_path | Participation: min(max_participation_pct, mult * mean(turnover)*100); impact linear then capped. |
| **Calibration harness** | methods_and_limits §13, acceptance spec | `crypto_analyzer/stats/calibration/`; tests: test_calibration_harness_type1, test_calibration_*_smoke.py | N/A (CI only) | Wide tolerances; Type I / FDR guards. Not full statistical certification. Seeds via rng_for(run_key, SALT_CALIBRATION) when run_key set. |

## Checklist of what was verified

- [x] dataset_id_v2: allowlist, ordering, STRICT/FAST_DEV, canonical encoding (dataset_v2.py)
- [x] run_key / run_instance_id: compute_run_key, build_run_identity (core/run_identity.py)
- [x] seed_root: signature (run_key, salt, fold_id, version), rng.py and SEED_ROOT_VERSION
- [x] RC/RW: run_reality_check output keys (requested_n_sim, actual_n_sim, null_construction_spec, component_salt, seed_root, rw_adjusted_p_values)
- [x] Schema versions: VALIDATION_BUNDLE, RC_SUMMARY, FOLD_CAUSALITY_ATTESTATION (contracts + fold_causality/attestation.py)
- [x] Fold attestation: build_fold_causality_attestation fields and validate_attestation
- [x] DSR: formula (Var with skew/kurtosis), E[max] = σ√(2 ln N), deflated_sr = (raw_sr - e_max)/std_sr (multiple_testing.py)
- [x] Neff: effective_trials_eigen formula and artifact keys
- [x] BH/BY: adjust() formula, NaN drop, monotonicity (multiple_testing_adjuster.py)
- [x] Stationary bootstrap: geometric block length, wrap-around (statistics.py)
- [x] RC: max statistic, shared indices, p-value formula (reality_check.py)
- [x] RW: stepdown order, monotonicity, NaN skip (reality_check.py)
- [x] CSCV PBO: pbo_cscv split construction, skip conditions, artifact keys (multiple_testing.py)
- [x] HAC: newey_west_lrv, hac_mean_inference, min_obs, lag rule (statistics.py); report keys t_hac_mean_return, p_hac_mean_return
- [x] Structural breaks: CUSUM / sup-Chow, run_break_diagnostics output shape (structural_breaks.py)
- [x] Capacity curve: participation vs power-law, CSV contract, non_monotone flag (execution_cost.py)
- [x] Calibration: what CI tests (BH/BY, RC, RW, CSCV) and wide-tolerance wording

## Known deviations / TODO for future

Entries are labeled as:

- **Deviation from some academic presentations (benign):** Implementation differs from one common textbook or paper convention but is internally consistent and not a correctness bug.
- **Potential correctness risk (material):** May affect estimates, calibration, or interpretation; documented so reviewers can assess.

---

1. **CSCV PBO split sampling** — *Potential correctness risk (material)*  
   **Doc:** “If choose(S,S/2) exceeds max_splits, random-sample splits with seed.”  
   **Code:** Always uses `n_splits = min(total_comb, max_splits)` iterations, each with `rng.permutation(S)` (random partition). No enumeration of distinct choose(S,S/2) combinations when total_comb ≤ max_splits.  
   **Location:** `crypto_analyzer/multiple_testing.py` lines 76–91.  
   **Impact:** Methodological choice, not inherently wrong; still deterministic for fixed seed. **Risk:** May increase variance of the PBO estimate vs full enumeration of all splits (fewer distinct train/test partitions used when total_comb ≤ max_splits).

2. **DSR variance formula (appendix B.2.2)** — *Deviation from some academic presentations (benign)*  
   **Doc:** Some texts give Var(SR) with (γ₄ − 1)/4.  
   **Code:** Uses pandas excess kurtosis (κ = γ₄ − 3): term (kurt/4)*SR² = ((γ₄−3)/4)*SR².  
   **Location:** `crypto_analyzer/multiple_testing.py` line 145.  
   **Impact:** Doc in statistical_methods.md B.2.2 uses different convention; implementation is consistent with “excess kurtosis” wording elsewhere.

3. **Fold_causality_attestation schema version** — *Deviation from some academic presentations (benign)*  
   **Doc:** Schema versions listed in docs sometimes omit fold_causality.  
   **Code:** FOLD_CAUSALITY_ATTESTATION_SCHEMA_VERSION = 1 in `crypto_analyzer/fold_causality/attestation.py` (not in `contracts/schema_versions.py`).  
   **Impact:** Intentionally local to the fold_causality module (build/validate attestation and gating reference it there). A future refactor could centralize schema versions in `schema_versions.py`; no commitment to that change.

4. **Project name spelling** — *Deviation from some academic presentations (benign)*  
   **Doc:** Several docs said “Crypto-Analyzer”.  
   **Code:** Repo name is “Crypto-Anaylzer”.  
   **Impact:** Naming consistency only; docs updated to use “Crypto-Anaylzer” where referring to the repo/project.
