# Architecture integrity audit

Principal-engineer read-only audit. No code changed. Inputs: `docs/spec/master_architecture_spec.md`, pipeline_contracts, dependency_graph, interfaces, testing_acceptance, risk_audit, performance_scale, versioning_release, phased_execution, implementation_ledger. Codebase scanned for actual dataflow and boundaries.

---

## 1. Spec vs implementation drift (by pipeline stage)

| Stage | Spec (contract) | Actual implementation | Drift / notes |
|-------|------------------|------------------------|---------------|
| **Ingestion** | Provider chains (SpotPriceChain, DexSnapshotChain), resilience, quality gates → spot_price_snapshots, sol_monitor_snapshots, provider_health, universe_* | `cli/poll.py`: direct fetch + insert; `crypto_analyzer/db/migrations.py`: tables; no formal “chain” abstraction in poll; providers in `crypto_analyzer/providers/` (CEX/DEX, resilience) | Spec describes chain pattern; poll is script-style. Provider registry exists; ingestion contract largely met. |
| **Bar materialization** | load_snapshots() → bars_{freq}; deterministic UPSERT; bars_1D from bars_1h | `cli/materialize.py`: `load_snapshots()`, `load_bars()` from `crypto_analyzer/data.py`; _resample_pair, _materialize_1d_from_1h; tables created in materialize | Aligned. Idempotent UPSERT; invariants as specified. |
| **Factor model** | Rolling OLS; time alignment; “no leak” per-fold not enforced as contract | `crypto_analyzer/factors.py`: rolling_multifactor_ols, causal_rolling_ols; `factor_materialize.py` writes factor_model_runs, factor_betas, residual_returns. reportv2 uses in-memory build_factor_matrix + rolling_multifactor_ols | Factor materialization (v2) exists; reportv2 path does not always use materialized factor_run_id. Causal per-fold available; contract “not enforced” still accurate. |
| **Signal generation** | Signal panels; execution convention t+1 | `crypto_analyzer/alpha_research.py`, `signals_xs.py`, `cs_factors.py`, `cs_model.py`. Backtest uses position.shift(1) in `cli/backtest.py` | Aligned. residual path has allow_lookahead=False default (quarantined lookahead). |
| **Signal validation** | IC series, decay, forward returns; fail-fast on misalignment | `crypto_analyzer/alpha_research.py`: information_coefficient, ic_decay, compute_forward_returns. `integrity.py`: assert_* helpers; not all paths hard-block | Validation bundle emitted per signal in reportv2 (`validation_bundle.py`, `cli/research_report_v2.py`). Integrity mostly warn, not hard-block. |
| **Portfolio optimization** | Signal → weights; PSD cov; fallback rank-based | `crypto_analyzer/optimizer.py`, `portfolio_advanced.py`, `risk_model.py` (ensure_psd). reportv2 uses optimize_long_short_portfolio | Aligned. |
| **Backtest / walk-forward** | train/test no overlap; t+1 execution | `crypto_analyzer/walkforward.py`, `cli/backtest.py`, `cli/backtest_walkforward.py` | Aligned. |
| **Statistical correction** | Deflated Sharpe, PBO, block bootstrap; stationary option | `crypto_analyzer/multiple_testing.py`, `multiple_testing_adjuster.py`, `statistics.py`. Stationary bootstrap in statistics; RC in `stats/reality_check.py` | Implemented; deflated Sharpe warns on assumptions; BH/BY in adjuster. |
| **Reporting** | Traceability: git_commit, env fingerprint, dataset_id, output hashes | `crypto_analyzer/governance.py` (make_run_manifest, stable_run_id, get_git_commit), `dataset.py` (dataset_id), `experiments.py`, `artifacts.py` (SHA256). reportv2 saves manifest, run_registry | Aligned. |

---

## 2. Actual dependency flow (Mermaid)

See `actual_dependency_graph.mmd` for the full graph. Summary:

- **Data sources:** SQLite (migrations.py; then load_snapshots, load_bars, get_factor_returns in `data.py`).
- **Entry points:** poll → DB; materialize (load_snapshots → bars); reportv2 (get_research_assets → load_bars + get_factor_returns → factors → signals → validation → optimizer → costs → report + manifest + experiment registry).
- **Key modules:** `research_universe.get_research_assets` → `data.load_bars`; reportv2 imports alpha_research, factors, signals_xs, validation, validation_bundle, portfolio, portfolio_advanced, risk_model, optimizer, walkforward, multiple_testing, experiments, governance, dataset, artifacts, integrity.

---

## 3. Duplication inventory

| Location | What is duplicated | Preferred single place |
|----------|--------------------|-------------------------|
| **OLS / residual betas** | `compute_ols_betas` used in `crypto_analyzer/factors.py`, `alpha_research.py` (residual signal); also in `cli/scan.py`, `cli/analyze.py`, `cli/report_daily.py` for ad-hoc residual/compression | Keep in `crypto_analyzer/factors.py`; CLI/scan/analyze/report_daily should call factors or a thin wrapper; avoid reimplementing OLS elsewhere. |
| **Cost application** | Fee + slippage: `crypto_analyzer/portfolio.apply_costs_to_portfolio` → `execution_cost.apply_costs`; `cli/backtest.py` uses `ExecutionCostConfig` + `slippage_bps_from_liquidity` + `model.apply_costs`; reportv2 uses `apply_costs_to_portfolio(port_ret, turnover_ser, fee_bps, slippage_bps)` | Single place: `crypto_analyzer/execution_cost.py` (ExecutionCostModel). portfolio.py and backtest.py already delegate; ensure all cost paths go through execution_cost. |
| **Slippage proxy (capacity)** | `cli/scan.py` `_add_capacity_slippage_tradable` (est_slippage_bps, capacity_usd); `execution_cost.slippage_bps_from_liquidity` for per-bar proxy | execution_cost for bar-level slippage; scan’s capacity/slippage is research-only and can stay in scan but document as “research proxy only.” |
| **Resampling / bars from snapshots** | `cli/materialize.py` _resample_pair; `crypto_analyzer/data.load_snapshots_as_bars` | data.py for load contract; materialize owns bar table schema and UPSERT. Clear split; no merge needed. |
| **Regime logic** | `crypto_analyzer/regimes/` (detector, features, materialize, legacy); dashboard `add_regime_from_percentile` in `cli/app.py`; report_daily `regime_shift` | Regimes: `crypto_analyzer/regimes/` as canonical; dashboard/report_daily are legacy/display—document and consider calling regime_features or legacy helpers. |

---

## 4. Leakage-risk inventory (verified; no new vectors)

| Risk | Spec / risk_audit | Actual status |
|------|-------------------|----------------|
| **Full-sample beta in residual signal** | signal_residual_momentum_24h full-sample OLS = lookahead | **Fixed:** `alpha_research.signal_residual_momentum_24h(..., allow_lookahead=False)` default; lookahead path quarantined in `_signal_residual_momentum_24h_lookahead`. Tests: `tests/test_leakage_sentinel.py`. |
| **research_report.py residual** | Legacy report calls `signal_residual_momentum_24h(returns_df, args.freq)` with no explicit allow_lookahead | Default is False; therefore causal. Recommendation: add explicit `allow_lookahead=False` in `cli/research_report.py` for clarity. [DOC ONLY] |
| **Regime smoothing in test** | Only filtering allowed in test | `regimes/regime_detector.py`: smooth in test raises; filter-only. |
| **Cost/ADV from future** | Liquidity/ADV must be trailing | Backtest/slippage use per-bar liquidity (contemporaneous); execution_cost uses bar-level liquidity. No future-based ADV in current paths. |
| **Factor per-fold** | Factor fitting must be train-only per fold | reportv2 uses full-series rolling OLS for signals (no fold split in factor fit); factor_materialize has causal_rolling_ols with as_of_lag_bars. Walk-forward backtest does not re-fit factors per fold in reportv2 path—document as limitation. |

---

## 5. Reproducibility inventory

| Mechanism | Where | Notes |
|-----------|--------|--------|
| **dataset_id** | `crypto_analyzer/dataset.py`: compute_dataset_fingerprint, dataset_id_from_fingerprint | Deterministic from table summaries, row counts, min/max ts. |
| **run_id** | `crypto_analyzer/governance.py`: stable_run_id(payload) = SHA256(JSON) [:16] | Used in manifests and artifact paths. |
| **git_commit** | governance.get_git_commit() | In manifest and phase3 schema (e.g. schema_migrations_phase3). |
| **Manifests** | governance.make_run_manifest, save_manifest; run_registry.jsonl | run_id, created_utc, git_commit, env_fingerprint, dataset_id, etc. |
| **Artifact hashes** | artifacts.compute_file_sha256; write_json_sorted for deterministic JSON | Validation bundle and artifact paths; deterministic rerun test uses CRYPTO_ANALYZER_DETERMINISTIC_TIME. |
| **Determinism toggles** | CRYPTO_ANALYZER_DETERMINISTIC_TIME (timeutils); bootstrap/RC seeds (e.g. rc_seed=42) | Used in reportv2 deterministic rerun and factor materialize tests. |
| **factor_run_id / regime_run_id** | factor_materialize, regime_materialize: hash of config + dataset_id (and time when not deterministic) | Stable when deterministic time set. |
| **Bootstrap seed** | statistics.py, reality_check: seed parameter stored in artifacts | Reproducible with same seed. |

---

## 6. Performance hotspots (I/O + compute)

| Hotspot | Module(s) | Pattern | Severity |
|---------|-----------|--------|----------|
| **Rolling OLS (assets × time)** | `crypto_analyzer/factors.py`: rolling_multifactor_ols, causal_rolling_ols; Python loops over assets/time | O(A·T) iteration; per-step OLS. Dominant compute in factor path. | High (spec: cache factor outputs) |
| **Cross-sectional per-timestamp** | `crypto_analyzer/signals_xs.py`, `alpha_research.information_coefficient`: per-timestamp correlation/rank | O(T·A) or similar; Python loops. | Medium |
| **DB reads** | `data.load_bars`, `load_snapshots`; reportv2 loads full series | I/O scales with bars × assets. | Medium |
| **Materialization** | `cli/materialize.py`: resample + UPSERT per pair/freq | O(pairs × bars) resample and writes. | Medium |
| **Factor/regime cache** | `crypto_analyzer/stats/factor_cache.py`, `regime_cache.py`; reportv2 --no-cache | Cache hit skips factor/regime compute; reduces repeated OLS/regime work. | Mitigation in place |
| **RC null distribution** | `crypto_analyzer/stats/rc_cache.py` | RC null cache keyed by family_id+config+dataset+git avoids recompute. | Mitigation in place |

---

## 7. Testing cost drivers (full pipeline / heavy tests)

| Test(s) | What runs | Why costly |
|---------|-----------|------------|
| **test_reportv2_deterministic_rerun** | Two full reportv2 runs with mocked get_research_assets/get_factor_returns; compares bundle + manifest byte-identical | Runs main() twice; full reportv2 stack (signals, validation, portfolio, costs, artifacts). |
| **test_reportv2_regime_conditioned_artifacts**, **test_reportv2_regimes_optional**, **test_reportv2_reality_check_optional** | reportv2.main() with patches (get_research_assets, get_factor_returns, record_experiment_run) | Full reportv2 pipeline per test; multiple tests invoke main(). |
| **test_phase2_integration** | run_migrations → materialize_factor_run → record_experiment_run → null_suite → artifacts | E2E migrations + factor materialize + registry + null suite. |
| **test_provider_integration** | Full poll cycle with mocked HTTP to temp SQLite | Ingestion path end-to-end. |
| **test_factor_materialize**, **test_regime_materialize** | materialize_factor_run / materialize_regime_run with in-memory or temp DB | Factor/regime OLS and DB writes; multiple idempotent/deterministic cases. |
| **test_factor_cache_hit_skips_compute**, **test_regime_cache_hit_skips_compute** | materialize with use_cache=True/False; patch causal_rolling_ols or regime write | Intended to verify cache avoids compute; still run materialize path. |

Recommendation: Keep these as integration/contract tests; consider marking “reportv2 full run” tests as integration and running them in a separate pytest phase if suite time grows.

---

## 8. Recommended changes (10–20 items)

| # | Recommendation | Tag | Modules/files |
|---|-----------------|-----|----------------|
| 1 | Document in spec that reportv2 factor path does not use materialized factor_run_id by default; optional “use materialized factors” flag could align with factor_materialize. | [DOC ONLY] | docs/spec/master_architecture_spec.md, docs/spec/components/pipeline_contracts.md |
| 2 | Add explicit `allow_lookahead=False` in `cli/research_report.py` for signal_residual_momentum_24h call. | [SAFE REFACTOR] | cli/research_report.py |
| 3 | Document that walk-forward in reportv2 does not re-fit factors per fold (single full-series rolling OLS); add to risk_audit or pipeline_contracts. | [DOC ONLY] | docs/spec/components/risk_audit.md or pipeline_contracts.md |
| 4 | Unify cost entry points: ensure all callers use execution_cost (ExecutionCostModel / apply_costs); audit app.py, walkforward.py, reportv2 for any bypass. | [SAFE REFACTOR] | cli/app.py, crypto_analyzer/walkforward.py, cli/research_report_v2.py |
| 5 | Add “implementation stronger than spec” to drift_register: ValidationBundle per signal, ExecutionCostModel unified, BH/BY adjuster, stationary bootstrap, RC, regime detector, factor/regime caches, promotion workflow. | [DOC ONLY] | docs/audit/drift_register.md |
| 6 | Specify integrity hard-block policy: which assertions (e.g. index alignment, monotonic ts) should exit with non-zero vs warn; implement in integrity.py + reportv2. | [BEHAVIOR CHANGE] | crypto_analyzer/integrity.py, cli/research_report_v2.py |
| 7 | Add engine_version and config_version to experiments table and manifest (per versioning_release); store in record_experiment_run and make_run_manifest. | [SAFE REFACTOR] | crypto_analyzer/experiments.py, crypto_analyzer/governance.py, db migrations |
| 8 | Document scan.py _add_capacity_slippage_tradable as “research-only proxy”; do not use for promotion/execution evidence without explicit disclaimer. | [DOC ONLY] | cli/scan.py (docstring), docs/spec/components/risk_audit.md |
| 9 | Mark reportv2 full-run tests as integration (e.g. pytest mark) so they can be run separately for speed. | [SAFE REFACTOR] | tests/test_reportv2_*.py, pytest.ini or pyproject.toml |
| 10 | Add schema_migrations (versioned) to core run_migrations so all DBs get version tracking; phase3 already has schema_migrations_phase3. | [BEHAVIOR CHANGE] | crypto_analyzer/db/migrations.py, migrations_v2.py |
| 11 | Document that dashboard regime (add_regime_from_percentile) and report_daily regime_shift are legacy/display only; canonical regime is crypto_analyzer/regimes. | [DOC ONLY] | cli/app.py, cli/report_daily.py, docs/spec or audit |
| 12 | Ensure all CLI paths that use residual/OLS call factors.compute_ols_betas or causal path (not local reimplementation). | [SAFE REFACTOR] | cli/scan.py, cli/analyze.py, cli/report_daily.py (already use factors or alpha_research; verify no duplicate OLS). |
| 13 | Add “null suite” as mandatory gate in testing_acceptance: reports should be able to emit null results next to real signals; already implemented in null_suite + reportv2. | [DOC ONLY] | docs/spec/components/testing_acceptance.md |
| 14 | Profile rolling_multifactor_ols and causal_rolling_ols under T=4k, A=200; document baseline and target before vectorizing/Numba. | [DEFER] | crypto_analyzer/factors.py |
| 15 | Add latency/signal_lag_bars to execution convention doc and backtest contract (spec: “trade at t+lag”); implementation is currently t+1 only. | [DEFER] | docs/spec, cli/backtest.py |
| 16 | Document Romano–Wolf (implemented, opt-in) in interfaces and implementation_ledger. | [DONE] | docs/spec/components/interfaces.md, docs/spec/implementation_ledger.md — RW is implemented; rw_adjusted_p_values when enabled. See methods_and_limits.md §9. |
| 17 | Ensure experiment registry stores family_id and adjusted p-values when reportv2 runs with --reality-check and BH/BY; verify in tests. | [SAFE REFACTOR] | cli/research_report_v2.py, crypto_analyzer/experiments.py |
| 18 | Add “spec incomplete” to drift_register: ExecutionCostModel interface not fully reflected in spec (spread_vol_scale, participation impact optional); schema_plan factor_* / regime_* present in code, not all in core migrations. | [DOC ONLY] | docs/audit/drift_register.md |
| 19 | Require promotion evidence to include execution_evidence when target is accepted/candidate (already enforced in gating with allow_missing override); document in promotion workflow. | [DOC ONLY] | crypto_analyzer/promotion/gating.py, docs/spec |
| 20 | Keep SQLite as single source of truth; document DuckDB/Parquet as future option for heavy analytical tables only (per performance_scale). | [DOC ONLY] | docs/spec/components/performance_scale.md |

---

**Files changed (this audit):**  
- Added: `docs/audit/architecture_integrity_audit.md`

**Commands to run:**  
- None (read-only audit).

**What to look for:**  
- Use this doc plus `actual_dependency_graph.mmd` and `drift_register.md` for prioritization and spec updates.
