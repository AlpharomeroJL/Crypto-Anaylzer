# Crypto-Analyzer

A **crypto quant monitoring + research platform** using Dexscreener snapshot data: analytics, scanning, backtesting, and a Streamlit dashboard. Data is polled into SQLite; bars are materialized and used for features, scans, and backtests. **Research-only; no trading or execution.**

## Research principles

- **No look-ahead bias:** Indicators and strategy state are computed only from past data; walk-forward backtests fit on train and simulate on test with no overlap.
- **Out-of-sample validation:** Use `backtest_walkforward.py` for train/test folds and stitched equity to assess robustness.
- **Costs and capacity:** Backtests and scanner apply fee/slippage proxies and optional capacity (position vs liquidity); all outputs are research estimates, not orders.
- **Factor and residual lens:** BTC_spot (and optionally ETH_spot) factor returns support beta/excess and residual returns; residual momentum ranks assets by factor-hedged move.
- **Regimes:** A single market regime label combines dispersion z-score, vol regime, and beta state (macro_beta, dispersion, risk_off, chop) for narrative and filtering.
- **Signals journal:** Triggered research signals (e.g. beta compression, dispersion extreme, residual momentum) are logged to SQLite for monitoring; no execution.
- **Cross-sectional alpha (Milestone 3):** Information Coefficient (IC) measures how well a signal predicts forward returns; Spearman rank IC is used for robustness to outliers. Turnover measures how much the top/bottom portfolio changes each period (0–2 scale); high turnover increases costs. Portfolio construction uses vol targeting (default 15% annual vol), risk parity (inverse vol), and beta neutralization; long/short portfolios are research-only. Block bootstrap is used for Sharpe confidence intervals (block size ~ sqrt(n) preserves serial correlation). **This platform is research-only:** no order routing, execution, exchange keys, or broker integration.

## Architecture (ASCII)

```
  +------------------+     +------------------+
  | dex_poll_        |     | config.yaml /    |
  | to_sqlite.py     |---->| config.py        |
  | (60s poll)       |     | (DB, filters)    |
  +--------+---------+     +--------+----------+
           |                        |
           v                        v
  +------------------+     +------------------+
  | dex_data.sqlite  |<----| data.py         |
  | sol_monitor_     |     | (normalized     |
  | snapshots        |     |  load)          |
  +--------+---------+     +--------+----------+
           |                        |
           v                        v
  +------------------+     +------------------+
  | materialize_     |     | features.py     |
  | bars.py          |---->| (returns, vol,   |
  | bars_5min, 1h..  |     |  drawdown, etc) |
  +--------+---------+     +--------+----------+
           |                        |
           +--------+-------+------+
                    v        v      v
  +------------+  +--------+  +----------+  +---------------+
  | dex_       |  | dex_   |  | backtest |  | report_daily  |
  | analyze.py |  | scan.py|  | .py      |  | .py           |
  +------------+  +--------+  +----------+  +---------------+
                    |
                    v
  +------------------+
  | app.py           |
  | (Streamlit)      |
  +------------------+
```

## Prerequisites

- **Python 3.10+**
- **PowerShell** (Windows) or bash/zsh (macOS/Linux)

## Setup (Windows PowerShell)

```powershell
git clone <your-repo-url>
cd Crypto-Anaylzer

python -m venv .venv
.\.venv\Scripts\Activate
pip install -r requirements.txt
```

Optional: `pip install st-keyup` for dashboard shortcuts. Optional: `pip install PyYAML` for `config.yaml` (otherwise config uses defaults).

## Configuration

- **config.yaml** — DB path, table, price column, timezone, default freq/window, min liquidity, min vol24, min bars, bars_freqs.
- **Environment overrides:** `CRYPTO_DB_PATH`, `CRYPTO_TABLE`, `CRYPTO_PRICE_COLUMN`.

Default DB: `dex_data.sqlite`, table: `sol_monitor_snapshots`, price: `dex_price_usd`. For a generic `snapshots` table with `price_usd`, set table to `snapshots` and price column to `price_usd`.

## Run the stack

### 1. Poller (populate data)

```powershell
.\.venv\Scripts\Activate
python dex_poll_to_sqlite.py --interval 60
```

Leave running. Creates `dex_data.sqlite` and tables. DEX pairs come from `config.yaml` key `pairs` (each: `chain_id`, `pair_address`, optional `label`). Overrides: `--config PATH`, `--no-pairs-from-config`, `--pair CHAIN_ID:PAIR_ADDRESS` (repeatable), `--pair-delay SEC`.

### 2. Materialize bars (resampled OHLCV-style)

```powershell
python materialize_bars.py
# Or single freq:
python materialize_bars.py --freq 1h
```

Creates `bars_5min`, `bars_15min`, `bars_1h`, `bars_1D`. Idempotent; safe to run daily.

**Acceptance test (multi-DEX):** After running the poller ~5–10 minutes with multiple pairs (e.g. SOL/USDC, WETH/USDC, WBTC/USDC in `config.yaml`), materialize 1h bars and verify:

```powershell
python materialize_bars.py --freq 1h
python -c "import sqlite3; con=sqlite3.connect('dex_data.sqlite'); print(con.execute('SELECT DISTINCT base_symbol, quote_symbol FROM bars_1h;').fetchall())"
```

Expected: multiple tuples e.g. `('SOL','USDC'), ('WETH','USDC'), ('WBTC','USDC')`. Then:

```powershell
python dex_analyze.py --freq 1h --window 24
```

should show correlation matrix and beta_vs_btc for multiple assets.

### 3. Analyze (leaderboard + plots)

```powershell
python dex_analyze.py --freq 5min --window 288
python dex_analyze.py --freq 1h --top 10
```

### 4. Scanner (top opportunities)

```powershell
python dex_scan.py --mode momentum --freq 1h --top 20
python dex_scan.py --mode volatility_breakout --freq 1h --z 2.0
python dex_scan.py --mode mean_reversion --freq 1h --csv scan.csv --json scan.json
python dex_scan.py --mode momentum --alert
```

### 5. Backtest

```powershell
python backtest.py --strategy trend --freq 1h
python backtest.py --strategy volatility_breakout --freq 1h --csv trades.csv --plot plots
```

### 5b. Walk-forward backtest (OOS)

```powershell
python backtest_walkforward.py --strategy trend --freq 1h --train-days 30 --test-days 7 --step-days 7
python backtest_walkforward.py --strategy trend --freq 1h --expanding --csv folds.csv --plot wf_plots
```

Converts days to bars by freq; runs multiple folds and prints fold metrics plus stitched equity.

### 6. Dashboard

```powershell
streamlit run app.py
```

Open http://localhost:8501. Pages: Overview, Pair detail, Scanner, Backtest, Walk-Forward, Market Structure, Signals, **Research** (Universe, IC Summary, IC Decay, Portfolio, Regime Conditioning), **Institutional Research** (Signal Hygiene, Advanced Portfolio, Overfitting Defenses, Conditional Performance, Experiments). With fewer than 3 assets, Research shows a friendly message; Institutional Research degrades gracefully (e.g. 1 DEX pair).

### 7. Daily report (cron / Task Scheduler)

```powershell
python report_daily.py
python report_daily.py --out-dir reports --save-charts --top 5
```

Writes markdown report + CSV to `reports/`; optional PNG charts for top 5.

### 8. Research report (cross-sectional alpha)

```powershell
python research_report.py --freq 1h --save-charts
python research_report.py --freq 1h --top-k 3 --bottom-k 3 --horizons 1,2,3,6,12,24 --fee-bps 30 --slippage-bps 10 --out-dir reports
```

Produces a markdown report and CSV artifacts: universe summary, signal IC summary (mean IC, t-stat, hit rate, 95% CI), IC decay table, portfolio backtest (L/S momentum and residual momentum), and regime-conditioned performance. Requires **≥ 3 assets** (DEX pairs + spot); otherwise the report states "need >= 3 assets".

### 9. Research report v2 (Milestone 4 — institutional)

```powershell
python research_report_v2.py --freq 1h --save-charts
python research_report_v2.py --freq 1h --signals clean_momentum,value_vs_beta --portfolio advanced --cov-method ewma --n-trials 50 --out-dir reports
```

Adds: **orthogonalized signals** (cross-correlation before/after), **advanced portfolio** (constraints, beta neutrality, diagnostics), **deflated Sharpe** per portfolio, **PBO proxy** from walk-forward when available, **regime-conditioned metrics** (dispersion regime), and optional **lead/lag** plot data. See **Signal hygiene and risk models** and **Overfitting defenses** below. Dashboard: **Institutional Research** page with tabs Signal Hygiene, Advanced Portfolio, Overfitting Defenses, Conditional Performance, Experiments.

**Signal hygiene and orthogonalization:** Cross-sectional signals are z-scored and optionally winsorized; they can be **neutralized** to exposures (e.g. beta, vol, liquidity) via per-timestamp OLS residuals, and **orthogonalized** sequentially so that each signal is residual to the previous ones. This reduces redundancy and improves interpretability (e.g. *clean_momentum* = momentum orthogonal to beta/vol; *value_vs_beta* = residual momentum neutralized to beta + vol + liquidity).

**Risk model methods:** `crypto_analyzer.risk_model` provides **EWMA covariance** (halflife), **shrinkage to diagonal** (shrink parameter), **Ledoit–Wolf** (sklearn if available; otherwise diagonal-shrink fallback), and **ensure_psd** (nearest PSD via eigenvalue clipping). Use `estimate_covariance(returns_window_df, method="ewma"|"lw"|"shrink", **kwargs)` for a single entry point.

**Overfitting defenses (disclaimers):** **Deflated Sharpe ratio** adjusts for multiple testing / selection bias using an approximate expected maximum Sharpe under the null; assumptions (e.g. iid returns, normality of the Sharpe estimator) are rough — use for **research screening only**, not sole inference. **PBO proxy** (probability of backtest overfitting) from walk-forward folds is a heuristic (e.g. fraction of splits where train-best underperforms median in test); interpret with caution. **Reality-check style** warnings suggest controls when many signals/portfolios were tested.

**Experiment logging:** `crypto_analyzer.experiments.log_experiment(run_name, config_dict, metrics_dict, artifacts_paths, out_dir="reports/experiments")` writes a JSON (timestamp, git hash, config, metrics) and appends a row to `experiments.csv`. `load_experiments(out_dir)` returns a DataFrame of past runs. Used by `research_report_v2.py` and the Institutional Research → Experiments tab.

## Annualization and frequency

- **Log returns** are used for aggregation (additive over time; symmetric). Cumulative return = `exp(cumsum(log_return)) - 1`.
- **Periods per year** (for annualized vol and Sharpe):
  - **5min:** `12 * 24 * 365` = 105120
  - **15min:** `4 * 24 * 365` = 35040
  - **1h:** `24 * 365` = 8760
  - **1D:** 365
- **Annualized vol** = `vol_log_return * sqrt(periods_per_year)`.
- **Annual Sharpe** = `sharpe_per_bar * sqrt(periods_per_year)` (risk-free = 0; per-bar Sharpe = mean(log_return) / std(log_return)).
- **Max drawdown:** equity = exp(cumsum(log_return)), peak = cummax(equity), drawdown = equity/peak - 1, **max_drawdown** = min(drawdown) (most negative, e.g. -0.15 = 15% drawdown).
- **return_24h** (or equivalent):
  - **1h bars:** last 24 bars → exp(sum(log_return over 24)) - 1.
  - **5min bars:** 24h = 288 bars.
  - **15min bars:** 24h = 96 bars.
  - **1D bars:** one bar = one day; column still named return_24h (effectively 1-day return).

## Quality filters

Applied consistently in analyze, scan, and dashboard (config):

- `min_liquidity_usd` (e.g. 250_000)
- `min_vol_h24` (e.g. 500_000)
- `min_bars` (e.g. 48 for 1h)
- Optional: exclude stable/stable pairs (USDC/USDT, etc.) in mover scans.

## Limitations and future work

- **Poller:** Supports multi-DEX-pair polling via `config.yaml` `pairs` and `--pair`; spot SOL/ETH/BTC and schema are unchanged.
- **No execution:** Scanner and backtest are research-only; no exchange/API execution.
- **Slippage/fees:** Backtest uses configurable fee (bps) and a liquidity-based slippage proxy; document assumptions when sharing results.
- **Short history:** With only a few days of data, Sharpe/Sortino and rankings are unstable; volatility clustering and cumulative curves are still useful.
- **Future:** Multi-pair polling, more strategies, optional execution hooks, alerting (e.g. email/Telegram).

## Residual returns and regimes (plain English)

- **Residual return:** After regressing an asset’s return on factor returns (e.g. BTC, ETH), the leftover is the residual. High residual return means the asset moved more than the factor model explains (idiosyncratic move). Used for “residual momentum” and relative strength vs the market.
- **Regimes:** The app and report combine (1) **dispersion z** (are assets moving in lockstep or not?), (2) **vol regime** (rising/falling/stable), and (3) **beta state** (compressed/expanded/stable) into one label: **macro_beta** (low dispersion, market-driven), **dispersion** (high dispersion, relative value), **risk_off** (rising vol + compressed beta or low dispersion), **chop** (stable). Helps choose style (trend vs relative value) and filter signals.

## Project layout

| Path | Purpose |
|------|--------|
| `crypto_analyzer/` | Package: config, data, features, factors, regimes, signals, ui, walkforward, **research_universe**, **alpha_research**, **portfolio**, **statistics**, **signals_xs**, **risk_model**, **portfolio_advanced**, **evaluation**, **multiple_testing**, **experiments** |
| `config.yaml` / `config.py` | DB, table, filters, defaults (root wrapper → package) |
| `data.py` / `features.py` | Root wrappers → `crypto_analyzer` |
| `materialize_bars.py` | Build bars_5min, bars_1h, etc. from snapshots |
| `dex_analyze.py` | Leaderboard + plots |
| `dex_scan.py` | Scanner: momentum, vol breakout, mean reversion |
| `backtest.py` | Trend and vol-breakout backtest |
| `backtest_walkforward.py` | Walk-forward OOS backtest CLI |
| `app.py` | Streamlit dashboard |
| `report_daily.py` | Daily markdown + CSV (+ optional charts) |
| `research_report.py` | Research report: IC, decay, portfolio, regime (≥3 assets) |
| `research_report_v2.py` | M4 report: orthogonalized signals, advanced portfolio, deflated Sharpe, PBO, regime, lead/lag |
| `dex_poll_to_sqlite.py` | Poller |
| `tests/` | pytest: returns math, beta, residuals, walkforward, regimes, **alpha research**, **portfolio**, **statistics**, **test_milestone4** (signals_xs, risk_model, portfolio_advanced, evaluation, multiple_testing, experiments) |

## Docs in repo

- **docs/INSTITUTIONAL.md** — What makes the stack “institutional” (M4: signal hygiene, risk, constraints, overfitting defenses, experiments); research-only.
- **DEPLOY.md** — Deploying the dashboard.
- **HANDOFF_AUTOPOLLING.md** — Poller and NSSM (Windows).
- **WINDOWS_24_7.md** — Running the poller 24/7.

## License

See the repository for license information.
