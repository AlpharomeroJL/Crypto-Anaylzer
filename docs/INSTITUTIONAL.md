# What makes this stack “institutional” (research-only)

This one-pager summarizes the **institutional-grade robustness and portfolio research infrastructure** added in Milestone 4. The platform remains **research-only**: no execution code, no exchange keys, no order routing.

## 1. Robust signal engineering

- **Cross-sectional hygiene:** Z-score (with clipping) and winsorization at each timestamp to limit outlier impact.
- **Neutralization:** Signals are regressed on exposures (e.g. beta vs BTC, rolling vol, log liquidity) per timestamp; residuals form the neutralized signal. Fewer than three assets at a timestamp degrades gracefully (raw signal returned).
- **Orthogonalization:** Multiple signals are orthogonalized sequentially (each regressed on the previous and replaced by residuals), with a report of average cross-correlation before and after.
- **Exposure panel:** Builds beta_btc_72, rolling_vol_24h, turnover proxy, and optional log liquidity from returns (and optional liquidity data), aligned to signal shape.
- **Composite signals:** e.g. *value_vs_beta* (residual momentum neutralized to beta + vol + liquidity), *clean_momentum* (momentum orthogonalized to beta and vol).

## 2. Portfolio research at “fund style”

- **Constraints:** Max weight per asset, min liquidity filter, capacity-based position cap (capacity_usd proxy), exclusion by estimated slippage (est_slippage_bps &gt; max_slippage_bps).
- **Neutralities:** Beta neutrality to BTC_spot, dollar neutrality (sum of weights ≈ 0), gross leverage targeting.
- **Optimizer:** Heuristic when cvxpy is not installed: rank-based raw weights → beta neutralization → risk scaling (inverse vol / covariance diagonal) → clipping → renormalization. Returns weights plus diagnostics (achieved beta, gross/net exposure, #assets, top long/short).
- **Risk model:** EWMA covariance, shrinkage to diagonal, optional Ledoit–Wolf (sklearn if available; else diagonal-shrink fallback), and ensure_psd (nearest PSD).

## 3. Regime-aware evaluation

- **Conditional metrics:** Performance (Sharpe, CAGR proxy, max DD, hit rate, avg daily PnL, n) broken down by regime bucket (e.g. dispersion high/mid/low, or beta_state).
- **Stability report:** Rolling Sharpe, rolling IC mean, drawdown duration, “fragility score” (% negative months + worst rolling window).
- **Lead/lag analysis:** Correlation of signal vs forward/backward returns at multiple lags (e.g. -24..+24 for 1h); works with small universes.

## 4. Multiple-testing / overfitting defenses

- **Deflated Sharpe ratio:** Adjusts for selection bias / number of trials; uses approximate variance of the Sharpe estimator and optional skew/kurtosis. **Disclaimer:** Assumptions are rough; use for research screening only.
- **Reality-check style warning:** Message and suggested controls when many signals or portfolios were tested.
- **PBO proxy:** From walk-forward results, a proxy for “probability of backtest overfitting” (e.g. fraction of splits where train-best underperforms median in test). Interpret with caution.

## 5. Experiment tracking

- **Local, lightweight:** `log_experiment(run_name, config, metrics, artifacts_paths, out_dir)` writes a timestamped JSON (with git hash when available) and appends a row to `experiments.csv`.
- **Load:** `load_experiments(out_dir)` returns a DataFrame of past runs for comparison and reproducibility.

## What we do *not* do

- No execution or order routing.
- No exchange API keys or broker integration.
- No live trading; all outputs are research estimates and backtests.

## Verification

- **CLI:** `python research_report_v2.py --freq 1h --save-charts`
- **Dashboard:** Streamlit → **Institutional Research** (tabs: Signal Hygiene, Advanced Portfolio, Overfitting Defenses, Conditional Performance, Experiments)
- **Tests:** `python -m pytest tests/ -v --tb=short` (includes `tests/test_milestone4.py`)

Fallbacks used when optional deps are missing: **Ledoit–Wolf** uses diagonal shrinkage if sklearn is not installed; **portfolio optimizer** uses the heuristic (no cvxpy).
