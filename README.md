# Crypto Quantitative Research Platform

A Python research engine that collects real-time cryptocurrency data from decentralized exchanges, applies institutional-grade statistical analysis, and produces validated trading signals, backtests, and interactive dashboards -- all running locally with zero infrastructure.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-26%20suites-brightgreen.svg)](#testing)

> **Research-only.** This tool analyzes data and produces reports. It does not execute trades, hold API keys, or connect to any broker.

---

## About

Crypto Quantitative Research Platform ingests live DEX (decentralized exchange) and spot price data, builds normalized OHLCV bars, and runs a full quantitative research pipeline: factor modeling, signal discovery, portfolio construction, backtesting, and regime detection. It applies the same statistical rigor used at institutional equity desks -- factor decomposition, walk-forward validation, and overfitting controls -- to the crypto ecosystem.

Everything runs from a single SQLite file. No cloud services, no paid APIs, no infrastructure to manage.

---

## Main Features

- **Automated data collection** from Dexscreener, Coinbase, and Kraken (no API keys needed) with automatic universe discovery of the most liquid DEX pairs
- **Multi-factor modeling** that decomposes every asset's returns into systematic factor exposure (BTC + ETH) and an idiosyncratic residual via rolling OLS regression, answering the question: *"Is this asset actually outperforming, or is it just moving with Bitcoin?"* Falls back gracefully to BTC-only when ETH spot data is unavailable.
- **Cross-sectional multi-factor model** scoring assets per timestamp using size (liquidity), volume, and momentum factors with configurable weights and winsorized z-scores
- **Signal validation** using Information Coefficient (rank correlation vs future returns), IC decay analysis, and signal orthogonalization to separate real predictive power from noise
- **Portfolio construction** with volatility targeting, beta-neutral weighting, constrained QP optimization (scipy), capacity-aware sizing, and realistic cost modeling (fees + liquidity-based slippage)
- **Local research API** (FastAPI) exposing health, experiments, metrics history, and latest reports over REST — no auth, read-only
- **Walk-forward backtesting** with strict no-lookahead train/test splits, deflated Sharpe ratios, and probability-of-overfitting estimates -- because a backtest that doesn't guard against overfitting is just curve-fitting
- **Regime detection** that classifies market conditions (risk-off, high dispersion, beta compression) and breaks down performance by regime, so you know *when* a strategy works, not just *whether* it works
- **Reproducibility and governance** with run manifests that record git commit, environment, data window, and SHA256 hashes of every output artifact
- **Experiment registry** backed by SQLite (with optional Postgres backend) that persists run metadata, hypothesis, tags, metrics, and artifacts so runs can be compared over time — with a dedicated Streamlit "Experiments" page supporting tag/hypothesis filtering, run comparison, and metric history charts
- **Interactive Streamlit dashboard** with 12 pages: leaderboard, scanner, backtester, market structure, signal journal, research, experiments, and governance views

---

## What Makes This Different

| Typical Retail Crypto Tools | This Platform |
|---|---|
| Show price charts and moving averages | Decomposes returns into factor exposure + idiosyncratic alpha via OLS regression |
| Backtest on a single asset with no overfitting checks | Walk-forward validation with deflated Sharpe, PBO proxy, and block bootstrap confidence intervals |
| Treat all crypto as independent | Models cross-sectional structure: correlation, dispersion, beta compression across the full universe |
| Use correlation as a proxy for factor exposure | Uses OLS beta decomposition that produces residuals with zero factor exposure by construction |
| No cost modeling or liquidity awareness | Fees (bps) + liquidity-dependent slippage proxy + capacity-constrained position sizing |
| No audit trail | Every run logs a manifest with git commit, env fingerprint, data window, output file hashes; plus a SQLite experiment registry for cross-run comparison |

**The core idea:** Most tokens move with BTC. If you don't strip out that market beta first, you can't tell whether a "signal" is real alpha or just noise correlated with Bitcoin. This platform does that decomposition systematically across every asset in the universe.

---

## Architecture

```
 Ingestion          Storage             Materialization       Research & Visualization
┌──────────┐      ┌──────────────┐      ┌──────────────┐      ┌───────────────────────┐
│ DEX APIs │─────▶│   SQLite DB  │─────▶│  OHLCV Bars  │─────▶│  Factor Models        │
│ Spot APIs│      │  (snapshots) │      │ 5m/15m/1h/1D │      │  Regime Detection     │
└──────────┘      └──────────────┘      └──────────────┘      │  Signal Validation    │
                                                               │  Portfolio Research   │
                                                               │  Streamlit Dashboard  │
                                                               └───────────────────────┘
```

**Single source of truth:** All analytics consume the same SQLite database. Bar construction is deterministic and idempotent -- rerunning on the same data always produces identical output.

---

## Quick Demo

One command does everything: preflight, data collection (if needed), bar materialization, research report, and experiment recording.

```powershell
git clone <repo-url> && cd crypto-analyzer
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt

.\scripts\run.ps1 demo
```

This creates/uses `dex_data.sqlite`, writes a report to `reports/`, records an experiment with a `dataset_id`, and prints next-step commands for the API and dashboard.

---

## Quickstart

```bash
# Clone and set up
git clone <repo-url> && cd crypto-analyzer
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install -r requirements.txt

# Verify installation
.\scripts\run.ps1 doctor

# Collect data (auto-discovers top DEX pairs on Solana)
.\scripts\run.ps1 universe-poll --universe --universe-chain solana --interval 60

# Build OHLCV bars from raw snapshots
.\scripts\run.ps1 materialize --freq 1h

# Generate research report (IC, decay, portfolio, overfitting checks)
.\scripts\run.ps1 reportv2 --freq 1h --out-dir reports

# Launch interactive dashboard
.\scripts\run.ps1 streamlit
```

<details>
<summary><strong>Full CLI Reference</strong></summary>

| Command | Description |
|---------|-------------|
| `doctor` | Preflight checks: environment, dependencies, DB schema, pipeline smoke test |
| `poll` | Single-pair data poller (60s interval) |
| `universe-poll --universe ...` | Multi-asset universe discovery and polling |
| `materialize` | Build deterministic OHLCV bars (5min, 15min, 1h, 1D) |
| `analyze` | Leaderboard analysis with factor decomposition |
| `scan` | Multi-mode opportunity scanner (momentum, residual, vol breakout, mean reversion, cs_multifactor) |
| `report` | Cross-sectional research report (IC, decay, portfolio simulation) |
| `reportv2` | Advanced report (orthogonalization, PBO, deflated Sharpe, QP optimizer, hypothesis/tags) |
| `daily` | Daily market structure and signal report |
| `backtest` | Single-asset backtest (trend following, volatility breakout) |
| `walkforward` | Walk-forward backtest with out-of-sample fold stitching |
| `streamlit` | Interactive research dashboard (12 pages) |
| `api` | Local read-only research API (FastAPI, default localhost:8000) |
| `demo` | One-command demo: doctor, poll (if needed), materialize, reportv2, next steps |
| `check-dataset` | Print dataset_id, table summaries, and integrity stats |
| `test` | Run full pytest suite |

All commands are run as `.\scripts\run.ps1 <command> [args...]`

</details>

---

## Project Structure

```
├── config.yaml                  # Database, universe, and filter settings
├── requirements.txt             # Pinned dependencies
│
├── crypto_analyzer/             # Core library (27 modules)
│   ├── config.py                #   Configuration loader (YAML + env overrides)
│   ├── data.py                  #   Data loading (snapshots, bars, spot prices)
│   ├── features.py              #   Returns, volatility, drawdown, momentum, beta
│   ├── factors.py               #   Multi-factor OLS (BTC/ETH), rolling regression, residuals
│   ├── cs_factors.py            #   Cross-sectional factor construction (size, liquidity, momentum)
│   ├── cs_model.py              #   Cross-sectional signal combiner (linear, rank_sum)
│   ├── optimizer.py             #   Constrained QP portfolio optimizer (scipy SLSQP)
│   ├── experiments.py           #   SQLite experiment registry with hypothesis/tags
│   ├── experiment_store.py      #   Pluggable store: SQLite (default) or Postgres backend
│   ├── api.py                   #   Read-only REST research API (FastAPI)
│   ├── regimes.py               #   Market regime classification
│   ├── signals.py               #   Signal detection and journal logging
│   ├── portfolio.py             #   Vol targeting, risk parity, beta neutralization
│   ├── portfolio_advanced.py    #   Constrained optimization with capacity filters
│   ├── walkforward.py           #   Walk-forward train/test split engine
│   ├── alpha_research.py        #   Information coefficient, signal builders, decay
│   ├── signals_xs.py            #   Cross-sectional z-score and orthogonalization
│   ├── risk_model.py            #   Covariance estimation (EWMA, Ledoit-Wolf)
│   ├── statistics.py            #   Block bootstrap and confidence intervals
│   ├── multiple_testing.py      #   Deflated Sharpe, PBO proxy
│   ├── evaluation.py            #   Regime-conditioned performance, lead/lag
│   ├── research_universe.py     #   Universe builder with quality filters
│   ├── governance.py            #   Run manifests, git tracking, env fingerprint
│   ├── integrity.py             #   Data quality checks (monotonicity, positivity)
│   ├── artifacts.py             #   Artifact I/O and SHA256 hashing
│   ├── diagnostics.py           #   Stability, fragility, and health scoring
│   ├── dataset.py               #   Dataset fingerprinting and versioning (dataset_id)
│   └── doctor.py                #   Preflight system checks
│
├── cli/                         # Command-line entry points
│   ├── app.py                   #   Streamlit dashboard (10+ pages)
│   ├── poll.py                  #   Data ingestion poller
│   ├── materialize.py           #   OHLCV bar builder
│   ├── scan.py                  #   Opportunity scanner
│   ├── analyze.py               #   Leaderboard with factor decomposition
│   ├── backtest.py              #   Single-asset backtester
│   ├── backtest_walkforward.py  #   Walk-forward backtest runner
│   ├── research_report.py       #   Cross-sectional research report
│   ├── research_report_v2.py    #   Advanced report (orthogonalization, PBO, QP)
│   ├── report_daily.py          #   Daily signal and market structure report
│   ├── api.py                   #   Local research API launcher (uvicorn)
│   ├── demo.py                  #   One-command demo (doctor + poll + materialize + report)
│   └── dashboard.py             #   Bloomberg-style terminal dashboard
│
├── tools/                       # Utility and maintenance scripts
├── scripts/                     # PowerShell runners and service configs
├── tests/                       # 26 pytest suites
├── pyproject.toml               # Package metadata; pip install -e . / -e ".[api,postgres]"
└── docs/                        # Architecture, deployment, and methodology
```

---

## Data Pipeline

**Ingestion** -- The poller collects data every 60 seconds from two sources: DEX pair data (price, liquidity, volume) from the Dexscreener public API, and spot reference prices (BTC, ETH, SOL) from Coinbase/Kraken. In universe mode, it automatically discovers and ranks the top liquid pairs with configurable quality filters and churn controls.

**Materialization** -- Raw snapshots are aggregated into deterministic OHLCV bars at four frequencies (5min, 15min, 1h, 1D). The process is idempotent: same input always produces the same output.

**Governance** -- Every research run writes a manifest recording the git commit, Python environment, data window, output SHA256 hashes, and computed metrics, creating a complete audit trail. Additionally, runs are recorded in a SQLite experiment registry (`reports/experiments.db`) for cross-run metric comparison via the Streamlit "Experiments" page.

**Dataset versioning** -- Each research run computes a `dataset_id`: a deterministic SHA-256 hash of the database fingerprint (table row counts, timestamp ranges, integrity stats). The same data always produces the same `dataset_id`, making it easy to tell whether two experiments ran against identical data. `.\scripts\run.ps1 doctor` prints the current `dataset_id`, and every experiment row in the registry includes it for reproducibility.

**Quick demo:**
```powershell
.\scripts\run.ps1 doctor
.\scripts\run.ps1 universe-poll --universe --universe-chain solana --interval 60
.\scripts\run.ps1 materialize --freq 1h
.\scripts\run.ps1 reportv2 --freq 1h --out-dir reports --hypothesis "baseline momentum" --tags "v1,momentum"
.\scripts\run.ps1 streamlit
```

---

## Install

```bash
pip install -e .              # core (numpy, pandas, streamlit, plotly)
pip install -e ".[api]"       # + FastAPI / uvicorn for local research API
pip install -e ".[postgres]"  # + SQLAlchemy / psycopg2 for Postgres experiment backend
pip install -e ".[dev]"       # + pytest
```

Or use `requirements.txt` for a fully pinned environment.

---

## Local Research API

```bash
.\scripts\run.ps1 api                        # start on localhost:8000
# or: python cli/api.py --host 0.0.0.0 --port 8000

curl http://localhost:8000/health
curl http://localhost:8000/experiments/recent?limit=5
curl http://localhost:8000/metrics/sharpe/history
```

Endpoints: `/health`, `/latest/allowlist`, `/experiments/recent`, `/experiments/{run_id}`, `/metrics/{name}/history`, `/reports/latest`. All read-only, no auth.

---

## Experiment Registry

Experiments are recorded automatically by `reportv2`. Use `--hypothesis` and `--tags` for queryable metadata:

```powershell
.\scripts\run.ps1 reportv2 --freq 1h --hypothesis "test residual momentum" --tags "momentum,v2"
```

Set `EXPERIMENT_DB_DSN` to a Postgres connection string for cloud-backed storage (optional; SQLite is the default):

```bash
export EXPERIMENT_DB_DSN="postgresql://user:pass@host:5432/experiments"
```

---

<details>
<summary><strong>Engineering Decisions (for the technically curious)</strong></summary>

| Decision | Why |
|----------|-----|
| **SQLite over Postgres** | Zero-config, single-file portability. Research-scale data (millions of rows) doesn't need a server database. |
| **Log returns throughout** | Additive across time, symmetric, mathematically correct for multi-period aggregation. Arithmetic returns only at display time. |
| **OLS regression for factor decomposition** | Produces residuals with exactly zero factor exposure by construction. Correlation alone can't decompose returns. |
| **Walk-forward over k-fold** | Time series has autocorrelation. Walk-forward with strict train/test separation prevents lookahead bias. |
| **Spearman rank IC for signal evaluation** | Robust to the fat-tailed distributions that are ubiquitous in crypto. Linear regression IC would be dominated by outliers. |
| **Block bootstrap for confidence intervals** | Preserves serial correlation structure in financial returns. Standard i.i.d. bootstrap produces overconfident intervals. |

</details>

---

## Testing

```bash
.\scripts\run.ps1 test
```

26 test suites covering: return computation correctness, multi-factor OLS decomposition, cross-sectional factor model, constrained QP optimizer, experiment registry (SQLite + metadata/tagging), experiment store (SQLite/Postgres), REST API smoke tests, console entrypoints, portfolio construction, walk-forward split generation (no lookahead), statistical methods (bootstrap, IC), universe management (churn control, deterministic ranking), governance (manifests, hashing), and data integrity assertions.

---

## Technology Stack

| Layer | Technology |
|-------|------------|
| **Core** | Python 3.10+, pandas, NumPy, SciPy |
| **Storage** | SQLite (default), Postgres (optional via `EXPERIMENT_DB_DSN`) |
| **API** | FastAPI + Uvicorn (optional `[api]` extra) |
| **Visualization** | Streamlit, Plotly, Matplotlib |
| **Statistics** | SciPy (QP optimizer), scikit-learn (optional: Ledoit-Wolf) |
| **Data Sources** | Dexscreener, Coinbase, Kraken (no API keys) |
| **Testing** | pytest (26 suites) |
| **Deployment** | NSSM Windows service (optional 24/7 polling) |

---

## Documentation

| Document | Contents |
|----------|----------|
| [Architecture](docs/architecture.md) | Module-level diagram and responsibility matrix |
| [Contributing](docs/contributing.md) | Code style, testing, and research-only boundary |
| [Deployment](docs/deployment.md) | Windows service setup for 24/7 operation |
| [Institutional Principles](docs/institutional.md) | Research standards and validation methodology |

---

## License

MIT License. See [LICENSE](LICENSE).
