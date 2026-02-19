# Phase 3 Slice 3: Dynamic beta estimator (Kalman/RLS) — alignment

**Canonical spec:** [master_architecture_spec.md](master_architecture_spec.md), [interfaces.md](components/interfaces.md), [schema_plan.md](components/schema_plan.md), [testing_acceptance.md](components/testing_acceptance.md), [risk_audit.md](components/risk_audit.md), [phased_execution.md](components/phased_execution.md).

## Estimator name and config

- **Estimator name:** `kalman_beta` (single standard name; no "dynamic_beta" alias in config).
- **FactorMaterializeConfig:** `estimator: str = "rolling_ols"` (default unchanged); when `estimator == "kalman_beta"` use RLS/Kalman-style estimator.
- **params (for kalman_beta):**
  - `process_var` (float, optional): state noise variance q; default 1e-5. Not used when `forgetting_factor` is set.
  - `obs_var` (float, optional): observation noise variance r; default 1e-4; always used in innovation variance S.
  - `init_P` (float, optional): initial P (covariance) scale; default 1.0 (identity scale).
  - `forgetting_factor` (float, optional): 0 < λ ≤ 1; if set, **takes precedence**: prediction step uses P_pred = P/λ only (process_var ignored); RLS-style forgetting. Stored in params_json when provided.
- **Precedence:** When `forgetting_factor` is set, the prediction step uses P_pred = P/λ only; `process_var` is not used. `obs_var` is always used in S = max(x'Px + r, eps) for numeric stability.

## Numeric stability

- **Innovation variance:** S = x'Px + obs_var is clamped with max(S, eps) (eps=1e-12) so the Kalman gain K = Px/S never blows up when f_t is near-zero or P is ill-conditioned.
- **Covariance symmetry:** After each prediction and update, P is replaced by (P + P')/2 so it stays symmetric and avoids drift from floating-point.

## Causality semantics

- **as_of_lag_bars >= 1:** Enforced in code (raise ValueError with message "as_of_lag_bars must be >= 1 to avoid fit including t+1 (no lookahead)").
- **Beta at t:** Uses only observations with index ≤ t - as_of_lag_bars for the update that produces the beta used at row t. At output row i we use the RLS state after processing observations 0, …, i - as_of_lag_bars.
- **Residual at t:** y_t - (alpha_t + X_t @ beta_t) where beta_t (and alpha_t) are from the causal state (no t+1 data).

## Persistence mapping (unchanged)

- **factor_model_runs:** factor_run_id, created_at_utc, dataset_id, freq, window_bars, min_obs, factors_json, **estimator** ("rolling_ols" | "kalman_beta"), params_json.
- **factor_betas:** factor_run_id, ts_utc, asset_id, factor_name, beta, alpha, r2 — same schema; fill from betas_dict, alpha_df, r2_df.
- **residual_returns:** factor_run_id, ts_utc, asset_id, resid_log_return — same schema; fill from residual_df.
- Insert ordering: sorted(common_idx), sorted(asset_cols), sorted(factor_names); beta_rows by (ts_utc, asset_id, factor_name); resid_rows by (ts_utc, asset_id).

## Output format (match causal_rolling_ols)

- **betas_dict:** dict[factor_name] -> DataFrame(index=common_idx, columns=asset_cols).
- **r2_df:** DataFrame(index=common_idx, columns=asset_cols).
- **residual_df:** DataFrame(index=common_idx, columns=asset_cols).
- **alpha_df:** DataFrame(index=common_idx, columns=asset_cols).
- Stable iteration: sorted index, sorted assets, sorted factor names.

## Tests and acceptance criteria

1. **test_as_of_lag_bars_must_be_at_least_one (dynamic beta):** dynamic_beta_rls(..., as_of_lag_bars=0) raises ValueError.
2. **test_dynamic_beta_deterministic:** Same returns_df and params => identical betas_dict, residual_df (and thus identical materialized rows).
3. **test_dynamic_beta_tracks_shift:** Synthetic data with a beta shift; dynamic beta should adapt (e.g. lower MSE or higher correlation with true beta after shift than rolling OLS with same window).
4. **test_materialize_kalman_beta_writes_tables:** FactorMaterializeConfig(estimator="kalman_beta", params={...}) => factor_model_runs row, factor_betas rows, residual_returns rows.
5. **test_materialize_kalman_beta_idempotent:** Second materialize same config => same factor_run_id, same row counts, overwrite not duplicate.
6. **Leakage sentinel:** Returns where y_t is correlated with factor_{t+1}; with as_of_lag_bars=1, residual/IC should not show abnormal exploit (same spirit as test_causal_residuals_no_future_data / test_leakage_sentinel).

## Deferrals

- Romano–Wolf, full sweep registry, UI promotion workflow — out of scope for Slice 3.
