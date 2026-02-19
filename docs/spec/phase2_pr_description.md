# Phase 2 merge — PR description (copy/paste)

Use the bullets below in the PR description when cutting the Phase 2 merge.

---

## Evidence bullets

- **Migration safety:** Versioned migrations in `migrations_v2.py`; `run_migrations(conn, db_path)` copies the on-disk DB before applying new migrations and restores from backup on failure. Idempotent: `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`; `schema_migrations` rows are only inserted for new versions. Failure-restore test verifies DB contents (e.g. `factor_model_runs` row) unchanged after simulated failure.

- **Factor materialization:** `factor_run_id` is a stable hash of canonical JSON (sorted keys) + `dataset_id` (no timestamps). Materialize is idempotent (same `factor_run_id` → delete then insert; no duplicates). Inserts are deterministic ordered (ts_utc, asset_id, factor_name) so reruns are hash-identical under deterministic mode. `causal_rolling_ols()` and residual writes enforce `as_of_lag_bars >= 1` (no fit-includes-t+1).

- **Multiple testing (BH/BY):** Family membership is deterministic (same run config → same signal set → same family). Reportv2 stores `p_value_raw_<signal>`, `p_value_adj_bh_<signal>`, and `p_value_family_adjusted` (0 when single signal / unadjusted, 1 when family exists and BH applied). Promotion/acceptance uses adjusted p-values only when family exists; no silent mixing. Rerun recomputes from raw p-values so no double-adjust. *Best practice (follow-up):* define `family_id = hash(config + signal list + horizon list + parameter grid id)` for explicit family identity.

- **Null suite:** Nulls are generated without touching future returns in construction (permutations of signal only; forward returns used only for evaluation). Time-dependent null (#3) uses block shuffle preserving within-block dependence. Output artifacts are deterministic for a fixed seed. CLI: `.\scripts\run.ps1 null_suite`; artifacts: `null_ic_dist.csv`, `null_sharpe_dist.csv`, `null_pvalues.json`.

- **Execution (spread/impact/capacity):** Spread proxy and participation-based impact are opt-in via config (`spread_vol_scale=0`, `use_participation_impact=False` by default; no silent change to existing behavior). Capacity curve uses fixed cost model (fee_bps, slippage_bps) and only varies notional multiplier/participation. Unit tests verify monotonicity: lower liquidity / higher vol → higher spread; higher participation → higher impact.

- **CTO notes:** (1) Migration runner: `run_migrations(conn, db_path=None)` degrades gracefully (no backup when `db_path` is None); ingest and read_api pass `db_path`. Tests that call migrations without path get a log that backup is disabled. (2) Reportv2 family: family is implicitly “all signals in this run”; explicit `family_id` hash recommended for future sweep/promotion workflows.

- **Verification:** `.\scripts\run.ps1 verify` passes (doctor, pytest, ruff, research-only, diagrams). Phase 2 unit tests: `test_migrations_v2_*`, `test_factor_materialize_*`, `test_multiple_testing_adjuster_*`, `test_null_suite_*`, `test_execution_cost_*`; E2E: `test_phase2_e2e_migrations_factor_registry_null_artifacts`. Determinism: set `CRYPTO_ANALYZER_DETERMINISTIC_TIME` for reproducible factor materialization and report artifacts.
