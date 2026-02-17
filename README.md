# Crypto-Analyzer

> Systematic digital asset research platform focused on factor modeling, regime detection, and robust validation.

A cross-asset quantitative research engine for digital asset markets. It combines DEX snapshot data with spot series, resampled bars, and factor-based analytics to support cross-sectional alpha validation, risk-aware portfolio construction, and statistically robust backtesting. The stack is **research-only**: no execution, no API keys for trading, no order routing.

---

## Architecture

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

---

## Data Flow

1. **Ingestion:** Poller (`dex_poll_to_sqlite.py`) writes snapshot data to SQLite at a configurable interval. Config (YAML + env) defines DB path, table, and filters.
2. **Resampling:** `materialize_bars.py` builds OHLCV-style bars (5min, 15min, 1h, 1D) from snapshots. Bars are idempotent and time-aligned.
3. **Features:** Returns, volatility, drawdown, and related series are computed from bars via `features.py` (log returns, annualization by frequency).
4. **Downstream:** Analytics (`dex_analyze.py`), scans (`dex_scan.py`), backtests (`backtest.py`, `backtest_walkforward.py`), and reports consume bars and features. The Streamlit app (`app.py`) reads from the same DB and config.

---

## Research Modules

- **Factors:** BTC (and optionally ETH) spot returns as factor series; beta and residual returns.
- **Regimes:** Combined regime label from dispersion z-score, vol regime, and beta state (macro_beta, dispersion, risk_off, chop).
- **Signals:** Research signals (e.g. beta compression, dispersion extreme, residual momentum) logged to SQLite; no execution.
- **Alpha research:** Cross-sectional IC (Spearman), IC decay, turnover; requires ≥3 assets.
- **Portfolio:** Vol targeting, risk parity, beta neutrality; long/short portfolios for research only.
- **Signal hygiene (v2):** Neutralization to exposures, sequential orthogonalization, composite signals (e.g. clean_momentum, value_vs_beta).
- **Risk model:** EWMA covariance, shrinkage, Ledoit–Wolf (optional), ensure_psd.
- **Experiments:** Local experiment logging (config, metrics, artifacts) for reproducibility.

See **docs/INSTITUTIONAL.md** for institutional research principles.

---

## Validation Framework

- **No look-ahead:** Indicators and strategy state use only past data; walk-forward backtests use strict train/test separation.
- **Walk-forward:** `backtest_walkforward.py` supports fixed or expanding windows and outputs fold metrics plus stitched equity.
- **IC and decay:** Spearman IC vs forward returns at multiple horizons; IC decay tables in reports and dashboard.
- **Bootstrap:** Block bootstrap for Sharpe (and related) confidence intervals where applicable.
- **Deflated Sharpe / PBO proxy:** Available in research_report_v2 and Institutional Research UI; documented as research screening tools with stated assumptions.

---

## Portfolio Construction

- **Vol targeting:** Default 15% annual vol; configurable.
- **Risk parity:** Inverse-vol weighting.
- **Beta neutrality:** Constraint vs primary factor (e.g. BTC).
- **Capacity and costs:** Optional capacity-based position caps; fee (bps) and liquidity-based slippage proxy in backtests and reports. All outputs are research estimates.

---

## Risk Controls

- **Quality filters (config):** min_liquidity_usd, min_vol_h24, min_bars; optional exclusion of stable/stable pairs.
- **Cost modeling:** Configurable fee and slippage proxy; document assumptions when sharing results.
- **Regime conditioning:** Performance can be evaluated by regime bucket (dispersion, vol, beta state).

---

## Reports

| Script | Purpose |
|--------|---------|
| `report_daily.py` | Daily markdown + CSV; optional PNG charts for top names. |
| `research_report.py` | Cross-sectional report: universe, IC summary, IC decay, portfolio backtest (L/S and residual momentum), regime-conditioned metrics. Requires ≥3 assets. |
| `research_report_v2.py` | Extended report: orthogonalized signals, advanced portfolio (constraints, beta neutrality), deflated Sharpe, PBO proxy, regime conditioning, optional lead/lag. |

Output directory: `reports/` (configurable via `--out-dir`). Under `reports/`: `csv/`, `charts/`, `manifests/`, `health/`. Research reports write run manifests (git commit, env fingerprint, data window, outputs with SHA256) to `reports/manifests/` when `--save-manifest` (default). V2 also writes a research health summary to `reports/health/health_summary.json`.

---

## Streamlit Interface

```powershell
streamlit run app.py
```

Open http://localhost:8501. Pages: Overview (universe size, top pairs by liquidity), Pair detail, Scanner, Backtest, Walk-Forward, Market Structure, Signals, **Research** (Universe, IC Summary, IC Decay, Portfolio, Regime Conditioning), **Institutional Research** (Signal Hygiene, Advanced Portfolio, Overfitting Defenses, Conditional Performance, Experiments), **Governance** (latest manifests, health summary, download manifest JSON). With fewer than 3 assets, Research shows a message; Institutional Research degrades gracefully.

---

## System Health Check

Run:

```powershell
python sanity_check.py
```

Inspection only (no logic changes). Validates: environment metadata, database existence and table row counts, critical CLI commands (materialize_bars, dex_analyze, dex_scan, report_daily, research_report, research_report_v2, pytest), and Streamlit/crypto_analyzer imports. Writes `reports/system_health_<UTC timestamp>.md` and exits 0 if all pass, 1 otherwise.

**Milestone 5 quick check:**

```powershell
python sanity_check_m5.py
```

Verifies M5 modules (governance, artifacts, spec, diagnostics, integrity), prints `RESEARCH_SPEC_VERSION`, runs a tiny manifest write/load in a temp dir, and prints the pytest command. Use after pulling to confirm governance and reproducibility paths.

**Example (pass):**

```
sanity_check: PASS (all critical commands and imports OK)
  Report: reports\system_health_2025-02-17T12_34_56Z.md
```

**Example (fail):**

```
sanity_check: FAIL
  Failed commands: research_report.py --freq 1h, pytest tests/ -q
  Warnings: 3
  Report: reports\system_health_2025-02-17T12_34_56Z.md
```

---

## Prerequisites and Setup

- **Python 3.10+**
- **Shell:** PowerShell (Windows) or bash/zsh (macOS/Linux)

```powershell
git clone <your-repo-url>
cd Crypto-Anaylzer

python -m venv .venv
.\.venv\Scripts\Activate
pip install -r requirements.txt
```

Optional: `pip install st-keyup` (dashboard shortcuts); `pip install PyYAML` (config.yaml; otherwise defaults).

---

## Configuration

- **config.yaml:** DB path, table, price column, timezone, default freq/window, min liquidity, min vol24, min bars, bars_freqs.
- **Environment:** `CRYPTO_DB_PATH`, `CRYPTO_TABLE`, `CRYPTO_PRICE_COLUMN`.

Default DB: `dex_data.sqlite`, table: `sol_monitor_snapshots`, price: `dex_price_usd`.

---

## Run the Stack

**1. Poller (populate data)**

```powershell
python dex_poll_to_sqlite.py --interval 60
```

Creates DB and tables. Pairs from `config.yaml` `pairs` or `--pair CHAIN_ID:PAIR_ADDRESS` (repeatable).

**Universe mode (multi-asset):** To poll top DEX pairs by chain from Dexscreener’s public API (no API keys), use either `--universe` or `--universe top`:

```powershell
python dex_poll_to_sqlite.py --universe top --universe-chain solana --universe-refresh-minutes 60 --interval 60
# or
python dex_poll_to_sqlite.py --universe --universe-chain solana --interval 60
```

Configure in `config.yaml` under `universe`: `enabled`, `chain_id`, `page_size`, `refresh_minutes`, `min_liquidity_usd`, `min_vol_h24`. If the universe fetch fails, the poller falls back to configured pairs.

**2. Materialize bars**

```powershell
python materialize_bars.py
# Or: python materialize_bars.py --freq 1h
```

**3. Analyze**

```powershell
python dex_analyze.py --freq 1h --window 24
python dex_analyze.py --freq 1h --top 10
```

**4. Scanner**

```powershell
python dex_scan.py --mode momentum --freq 1h --top 5
python dex_scan.py --mode volatility_breakout --freq 1h --z 2.0
```

**5. Backtest**

```powershell
python backtest.py --strategy trend --freq 1h
python backtest_walkforward.py --strategy trend --freq 1h --train-days 30 --test-days 7 --step-days 7
```

**6. Reports**

```powershell
python report_daily.py
python research_report.py --freq 1h --save-charts
python research_report_v2.py --freq 1h --save-charts
```

---

## Annualization and Frequency

- **Log returns:** Cumulative return = exp(cumsum(log_return)) − 1.
- **Periods per year:** 5min 105120, 15min 35040, 1h 8760, 1D 365.
- **Annualized vol** = vol_log_return × sqrt(periods_per_year).
- **Annual Sharpe** = sharpe_per_bar × sqrt(periods_per_year) (risk-free = 0).
- **Max drawdown:** equity = exp(cumsum(log_return)); drawdown = equity / cummax(equity) − 1.

---

## Limitations

- **Data:** Poller supports multi-DEX pairs via config; short history yields unstable Sharpe/rankings.
- **Execution:** None. Scanner and backtests are research-only; no exchange or broker integration.
- **Slippage/fees:** Backtest uses configurable fee and liquidity-based slippage proxy; document assumptions when sharing.

---

## Research-Only Disclaimer

This platform is for **research only**. It does not execute trades, connect to execution APIs, or use exchange keys for trading. All backtests, reports, and dashboard outputs are estimates for study and comparison. Any use for live or paper trading is outside the scope of this repository.

---

## Project Layout

| Path | Purpose |
|------|--------|
| `crypto_analyzer/` | Package: config, data, features, factors, regimes, signals, ui, walkforward, research_universe, alpha_research, portfolio, statistics, signals_xs, risk_model, portfolio_advanced, evaluation, multiple_testing, experiments |
| `config.yaml` / `config.py` | DB, table, filters, defaults |
| `materialize_bars.py` | Build bars from snapshots |
| `dex_analyze.py` | Leaderboard and plots |
| `dex_scan.py` | Scanner (momentum, vol breakout, mean reversion) |
| `backtest.py` / `backtest_walkforward.py` | Backtest CLIs |
| `app.py` | Streamlit dashboard |
| `report_daily.py` / `research_report.py` / `research_report_v2.py` | Reports |
| `dex_poll_to_sqlite.py` | Poller |
| `tests/` | pytest suite |

---

## Docs in Repo

- **docs/INSTITUTIONAL.md** — Institutional research principles (data, factors, validation, portfolio, regime, overfitting).
- **CONTRIBUTING.md** — Code style, testing, research-only boundary.
- **DEPLOY.md** — Deploying the dashboard.
- **HANDOFF_AUTOPOLLING.md** — Poller and NSSM (Windows).
- **WINDOWS_24_7.md** — Running the poller 24/7.

---

## License

See the repository for license information.
