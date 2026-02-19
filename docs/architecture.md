# Architecture

This expands the README’s high-level diagram with module responsibilities and data flow.

## Diagram

Data flow: **ingest** (poll) → SQLite (core + v2 + optional Phase 3) → materialize bars / factor / regime → research, backtests, reports, UI. Dashboard reads via **read_api** and **ingest.get_provider_health**; poll is the only writer path and uses **ingest** only.

```
  +----------------------+     +------------------+
  | cli/poll.py         |---->| config.yaml /    |
  | (ingest API only)   |     | config.py        |
  +----------+----------+     +------------------+
             |                         |
             v                         v
  +----------------------+     +------------------+
  | SQLite (db_path)     |<----| crypto_analyzer  |
  | run_migrations       |     | .ingest         |
  | (core + v2; phase3   |     | (get_poll_ctx,   |
  |  opt-in)             |     |  run_one_cycle)  |
  +----------+----------+     +------------------+
             |                         |
             v                         v
  +----------------------+     +------------------+
  | cli/materialize.py  |     | .read_api        |
  | bars_{freq}          |     | (allowlist,      |
  | factor_materialize   |     |  health views)    |
  | regime_materialize   |     +--------+--------+
  | (opt, phase3)         |              |
  +----------+----------+              |
             |                         v
             |              +------------------+
             |              | .data, .features |
             |              | .factors, .regimes|
             |              +--------+--------+
             |                       |
             +-----------+-----------+
                         v
  +--------+  +--------+  +----------+  +----------------+  +----------+
  | analyze|  | scan   |  | backtest*|  | report_*.py    |  | app.py   |
  |        |  |        |  | *_wf     |  | daily, R, Rv2  |  | Streamlit|
  +--------+  +--------+  +----------+  +----------------+  +----------+
  * backtest uses execution_cost (fees, slippage, capacity)
```

## Module responsibilities

| Module | Responsibility |
|--------|----------------|
| **crypto_analyzer.ingest** | Poll entry: get_poll_context(db_path) opens DB, run_migrations (core + v2), creates DbWriter, ProviderHealthStore, spot and DEX chains. run_one_cycle() writes snapshots, allowlist (universe mode). CLI must use ingest for poll; no direct db imports in poll. |
| **crypto_analyzer.read_api** | Read-only API for dashboard/CLI: load_spot_snapshots_recent, load_latest_universe_allowlist, load_universe_allowlist_stats, load_universe_churn_verification. Applies run_migrations on connect. Use instead of opening SQLite directly in UI. |
| **crypto_analyzer.db** | migrations.py (core schema, calls run_migrations_v2), migrations_v2.py (factor_model_runs, factor_betas, residual_returns, schema_migrations), migrations_phase3.py (regime_runs, regime_states; opt-in only, not called from run_migrations). writer.py, health.py. |
| **crypto_analyzer.config** | DB path, table, price column, filters, defaults; YAML + env overrides. |
| **crypto_analyzer.data** | Load snapshots, bars, spot series; append spot returns; get factor returns. |
| **crypto_analyzer.features** | Returns, vol, drawdown, momentum, beta/corr, dispersion, vol/beta regime, lookback helpers. |
| **crypto_analyzer.factors** | Multi-factor OLS (BTC/ETH spot), rolling regression, causal residuals (as_of_lag_bars). Falls back to BTC-only when ETH unavailable. |
| **crypto_analyzer.factor_materialize** | Materialize factor runs to DB: factor_model_runs, factor_betas, residual_returns (deterministic run_id, dataset_id). Used by reportv2/research pipeline. |
| **crypto_analyzer.cs_factors** | Cross-sectional factor construction: size (log liquidity), volume (log vol_h24), momentum (lookback return). Per-timestamp winsorized z-scores. |
| **crypto_analyzer.cs_model** | Cross-sectional signal combiner: linear weighted sum or rank_sum of factor scores. Default weights: size 0.2, liquidity 0.2, momentum 0.6. |
| **crypto_analyzer.optimizer** | Constrained QP (scipy SLSQP). Gross leverage, net exposure, max weight, long-only. Rank-based fallback on failure. |
| **crypto_analyzer.execution_cost** | Unified cost model: fees (bps), liquidity-dependent slippage, participation impact, capacity curve. Used by backtest and portfolio. |
| **crypto_analyzer.regimes** | Package: legacy classify_market_regime, explain_regime (dispersion_z, vol_regime, beta_state). Optional Phase 3: RegimeDetector (fit/predict), regime_features, regime_materialize (regime_runs, regime_states). Gated by CRYPTO_ANALYZER_ENABLE_REGIMES=1. |
| **crypto_analyzer.signals** | signals_log table; detect_signals (beta compression, dispersion extreme, residual momentum); log_signals. |
| **crypto_analyzer.signals_xs** | Cross-sectional z-score, orthogonalize_signals, build_exposure_panel. |
| **crypto_analyzer.walkforward** | walk_forward_splits, run_walkforward_backtest (train/test folds, no lookahead). |
| **crypto_analyzer.alpha_research** | IC, IC decay, forward returns, signal builders, rank_signal_df. |
| **crypto_analyzer.statistics** | Block bootstrap, significance_summary, safe_nanmean; optional stationary bootstrap. |
| **crypto_analyzer.multiple_testing** | Deflated Sharpe, PBO proxy, reality check. |
| **crypto_analyzer.multiple_testing_adjuster** | Family-wise p-value adjustment (BH, BY). |
| **crypto_analyzer.evaluation** | conditional_metrics, lead_lag_analysis (regime-conditioned). |
| **crypto_analyzer.validation_bundle** | Per-signal validation bundle (reportv2): IC, decay, turnover, paths. |
| **crypto_analyzer.experiments** | SQLite experiment registry: run metadata, hypothesis, tags, metrics, artifact hashes. |
| **crypto_analyzer.experiment_store** | Pluggable store: SQLiteExperimentStore (default), PostgresExperimentStore (EXPERIMENT_DB_DSN). get_experiment_store(). |
| **crypto_analyzer.api** | Read-only FastAPI: /health, /latest/allowlist, /experiments/recent, /experiments/{run_id}, /metrics/{name}/history, /reports/latest. |
| **crypto_analyzer.governance** | Run manifests, save_manifest, load_manifests; git tracking. |
| **crypto_analyzer.artifacts** | Artifact I/O, SHA256 hashing, snapshot_outputs, timestamped filenames. |
| **crypto_analyzer.dataset** | Dataset fingerprinting, dataset_id, fingerprint_to_json. |
| **crypto_analyzer.integrity** | Data quality checks, integrity checks used by reportv2. |
| **crypto_analyzer.diagnostics** | Health summary, rolling IC stability. |
| **crypto_analyzer.doctor** | Preflight: environment, dependencies, DB schema, pipeline smoke test. |
| **crypto_analyzer.null_suite** | Null/placebo runner: random ranks, permuted signal, block shuffle; write_null_suite_artifacts. |
| **crypto_analyzer.spec** | Research spec versioning; validate_research_only_boundary (verify step). |
| **crypto_analyzer.order_intent** | Execution boundary types (no live order submission). |
| **crypto_analyzer.ui** | safe_for_streamlit_df, format_percent/float/bps, st_df, st_plot. |
| **CLI** | poll.py (ingest), materialize.py, scan.py, analyze.py, research_report.py, research_report_v2.py, report_daily.py, backtest.py, backtest_walkforward.py, api.py, null_suite.py, demo.py. app.py (Streamlit) uses read_api and ingest.get_provider_health. |

## Data flow

1. **Poll** uses **crypto_analyzer.ingest** only: get_poll_context(db_path) runs run_migrations (core + v2), then run_one_cycle() writes to spot_price_snapshots, sol_monitor_snapshots, universe_allowlist / universe_churn_log (universe mode), provider_health. No direct db or provider imports in poll.py.
2. **read_api** is used by the dashboard for allowlist and health views; it opens DB read-only and applies run_migrations on connect. **ingest.get_provider_health** is used for provider status on the Runtime/Health page.
3. **materialize** (cli/materialize.py) builds bars_{freq} from snapshots. **factor_materialize** writes factor_model_runs, factor_betas, residual_returns (when running factor pipeline). **regime_materialize** (optional, Phase 3) writes regime_runs, regime_states after run_migrations_phase3; requires CRYPTO_ANALYZER_ENABLE_REGIMES=1.
4. **Analyze / Scan / Report / Reportv2** load bars and spot via data, compute features/factors/regimes (regimes.classify_market_regime from legacy), optionally use factor_materialize outputs and regime-conditioned IC when regimes enabled.
5. **Backtest** uses bars with execution_cost (fees, slippage, capacity). **backtest_walkforward** runs OOS folds.
6. **Streamlit** (app.py) uses data/features/regimes/signals for Overview, Scanner, Backtest, Walk-Forward, Market Structure, Signals, Research, Institutional Research, Experiments, Runtime/Health, Governance. Reads allowlist and health via read_api; provider status via ingest.get_provider_health.

## Research-only

No exchange keys, order placement, wallet signing, or position management. All outputs are for research and monitoring. **spec.validate_research_only_boundary** (run by `.\scripts\run.ps1 verify`) enforces forbidden keywords in source.
