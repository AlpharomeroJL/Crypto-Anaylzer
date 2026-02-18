# Institutional Research Principles

This document summarizes the research standards and controls implemented in the platform. Tone is descriptive; no execution or order routing is present.

---

## 1. Research-Only Architecture

- **No execution code.** All outputs are estimates, backtests, and reports. No order routing, exchange APIs, or broker integration.
- **No API keys.** Data ingestion uses configurable pollers and snapshot storage; no live trading or execution credentials.
- **Separation between research and deployment.** The codebase is a research engine. Any production deployment would sit outside this repo and consume only published methodology or artifacts.

---

## 2. Data Integrity

- **Resampling methodology.** Snapshots are resampled to OHLCV-style bars (5min, 15min, 1h, 1D) with consistent aggregation; bar construction is idempotent and time-aligned.
- **Log returns.** Returns are computed as log returns for aggregation (additive over time) and symmetric treatment; cumulative return = exp(cumsum(log_return)) − 1.
- **Annualization assumptions.** Periods-per-year are defined by frequency (e.g. 1h → 8760); annualized vol and Sharpe use sqrt(periods_per_year). Documented in README and config.
- **Quality filters.** Minimum liquidity, minimum 24h volume, minimum bar count, and optional exclusion of stable/stable pairs are applied consistently in analytics, scans, and the dashboard.

---

## 3. Factor Modeling

- **BTC beta modeling.** A single primary factor (BTC spot) is used for beta and excess returns; optionally ETH or other factors can be included. Beta is estimated over a configurable window.
- **Residual returns.** Asset returns are regressed on factor returns; residuals represent idiosyncratic move and drive residual momentum and relative strength.
- **Orthogonalization.** Multiple cross-sectional signals can be orthogonalized sequentially (each signal regressed on the previous, replaced by residuals) to reduce redundancy and improve interpretability.
- **Signal neutralization.** Signals are neutralized to exposures (e.g. beta, rolling vol, liquidity) via per-timestamp OLS residuals before use in portfolio or ranking.

---

## 4. Validation Discipline

- **Walk-forward validation.** Backtests support train/test splits and rolling or expanding walk-forward folds; no overlap between train and test.
- **Information coefficient (Spearman).** Cross-sectional signal quality is measured by Spearman rank IC vs forward returns; robust to outliers.
- **IC decay.** IC is computed at multiple forward horizons to assess signal decay and horizon stability.
- **Bootstrap confidence intervals.** Block bootstrap (e.g. block size ~ sqrt(n)) is used for Sharpe and related statistic confidence intervals where applicable.
- **Deflated Sharpe.** An adjustment for selection bias / multiple testing is available; assumptions are documented and the metric is for research screening only.
- **PBO proxy.** A heuristic proxy for “probability of backtest overfitting” from walk-forward folds (e.g. fraction of splits where train-best underperforms median in test); interpret with caution.

---

## 5. Portfolio Construction

- **Vol targeting.** Default target annual vol (e.g. 15%) is applied to scale portfolio weights.
- **Risk parity.** Inverse-vol or diagonal risk weighting is available for long/short construction.
- **Beta neutrality.** Portfolios can be constrained to zero (or target) exposure to the primary factor (e.g. BTC).
- **Capacity-aware filters.** Position size can be capped relative to liquidity; capacity and estimated slippage filters are available in advanced portfolio logic.
- **Cost modeling.** Backtests and reports apply configurable fee (bps) and a liquidity-based slippage proxy; all results are research estimates, not execution forecasts.

---

## 6. Regime Awareness

- **Vol regime classification.** Volatility is classified (e.g. rising, falling, stable) and used in narrative and filtering.
- **Beta compression.** Beta state (compressed vs expanded vs stable) is combined with dispersion and vol into a single regime label.
- **Dispersion index.** Cross-sectional dispersion (e.g. z-score of cross-sectional vol) indicates whether assets move in lockstep or not.
- **Regime-conditioned performance.** Metrics (Sharpe, drawdown, hit rate) can be broken down by regime bucket for conditional assessment.

---

## 7. Overfitting Controls

- **Multiple testing awareness.** When many signals or portfolios are tested, reality-check style warnings and suggested controls are surfaced.
- **Signal orthogonalization.** Redundancy among signals is reduced via sequential orthogonalization and reported (e.g. cross-correlation before/after).
- **Experiment logging.** Runs can be logged (config, metrics, artifacts, optional git hash) to a local experiments store for reproducibility and comparison; no external services required.

---

---

## 8. Governance and Reproducibility (Milestone 5)

- **Run manifests.** Each research report run can write a manifest (run_id, created_utc, git_commit, env_fingerprint, spec version, args, data_window, outputs with file SHA256, metrics, notes) to `reports/manifests/`. Enables auditability and reproducibility.
- **Research spec version.** A single `RESEARCH_SPEC_VERSION` (e.g. 5.0) and `spec_summary()` expose version and key module presence. Optional boundary check scans repo source for forbidden keywords (e.g. execution/keys) and raises if found; docs and the spec module itself are excluded.
- **Artifacts.** Centralized artifact I/O (UTF-8 CSV/JSON/text), directory creation, and file SHA256 hashing. Streamlit download buttons use bytes (e.g. `df.to_csv(...).encode("utf-8")`) to avoid type errors.
- **Diagnostics.** Fragility/stability (e.g. rolling IC stability), parameter sensitivity smoke (small grid), regime concentration, asset concentration, cost sensitivity. A `build_health_summary` aggregates data coverage, signal stability, overfitting proxies, regime dependency, capacity proxy. Research report v2 writes `reports/health/health_summary.json` and the dashboard Governance page shows latest manifests and health summary.
- **Data integrity checks.** Before forward returns: monotonic time index, no zero/negative prices, no forward-looking alignment. Checks emit warnings only; they do not crash the run.

---

## Multi-asset (universe) polling

- **Universe mode.** The poller can optionally fetch “top” DEX pairs for a chain via Dexscreener’s public search API (no API keys). Pairs are filtered by min liquidity and min 24h volume; the allowlist is refreshed at a configurable interval. All pairs are stored in the same `sol_monitor_snapshots` table. If the universe fetch fails, the poller tries relaxed thresholds, then optional config `universe.bootstrap_pairs`, then configured pairs.
- **Auditability.** Each universe refresh writes the active allowlist to the `universe_allowlist` table (timestamp, chain, pair, label, liquidity, volume, source, query_summary). This provides an audit trail for research governance: which pairs were in scope at each refresh and whether they came from normal discovery, relaxed filters, bootstrap, or config fallback.
- **Research modules.** Universe and research reports handle &gt;3 assets gracefully; quality filters and constant-return drops keep the research universe consistent.

---

*This platform is research-only: no order routing, execution, exchange keys, or broker integration.*
