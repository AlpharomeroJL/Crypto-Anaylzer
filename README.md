# Crypto Quantitative Research Platform

A local-first quantitative research engine for cryptocurrency markets. It ingests live data from decentralized and centralized exchanges, normalizes it into a single SQLite database, and runs institutional-grade statistical analysis — factor decomposition, cross-sectional signal validation, portfolio optimization, and walk-forward backtesting — all without API keys, cloud services, or trading execution.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-pytest-brightgreen.svg)](#testing)

> **Research-only.** This tool analyzes data and produces reports. It does not execute trades, hold API keys, or connect to any broker.

---

## What This Does (Plain English)

Cryptocurrency prices are noisy. Most tokens move in lockstep with Bitcoin — when BTC goes up 5%, nearly everything else does too. That makes it hard to tell whether a token is *actually* performing well, or just riding Bitcoin's coattails.

This platform answers that question rigorously:

1. **Collects data** from public exchange APIs every 60 seconds — DEX pair prices, liquidity, and volume from [Dexscreener](https://dexscreener.com), plus reference spot prices (BTC, ETH, SOL) from Coinbase and Kraken.

2. **Strips out market beta** using rolling OLS regression against BTC/ETH factors, producing a residual return for each asset that represents genuine idiosyncratic performance.

3. **Validates signals** using Information Coefficient analysis, IC decay curves, and cross-sectional orthogonalization — the same tools institutional equity desks use to separate real predictive power from noise.

4. **Constructs portfolios** with constrained quadratic optimization, volatility targeting, beta neutralization, and realistic cost modeling (exchange fees + liquidity-dependent slippage).

5. **Guards against overfitting** with walk-forward validation (strict train/test separation), deflated Sharpe ratios, and probability-of-backtest-overfitting estimates.

Everything lives in a single SQLite file. No infrastructure to manage, no cloud costs, no vendor lock-in.

---

## Why This Stack Is Different

| Typical Crypto Tools | This Platform |
|---|---|
| Show price charts with moving averages | Decomposes returns into factor exposure + idiosyncratic alpha via OLS regression |
| Backtest on a single asset, no overfitting checks | Walk-forward validation with deflated Sharpe, PBO proxy, block bootstrap CIs |
| Treat all crypto assets as independent | Models cross-sectional structure: correlation, dispersion, beta compression |
| No cost modeling | Fees (bps) + liquidity-dependent slippage + capacity-constrained sizing |
| Hardcoded to one exchange | **Extensible provider architecture** — add new CEX/DEX sources as plugins |
| No audit trail | Git-tracked run manifests, dataset versioning (SHA-256), SQLite experiment registry |
| Fragile data ingestion | Circuit breakers, retry/backoff, last-known-good caching, data quality gates |

**The core insight:** Most tokens move with BTC. If you don't strip out that market beta first, you can't tell whether a "signal" is real alpha or noise correlated with Bitcoin. This platform does that decomposition systematically across every asset, every timestamp.

---

## Architecture Overview

Ingestion uses the **ingest** API (poll context, provider chains, migrations). The dashboard and health views use the **read_api** for read-only DB access. The database has **versioned migrations**: core tables (from `run_migrations`), v2 factor tables (factor_model_runs, factor_betas, residual_returns), and optional Phase 3 regime tables (regime_runs, regime_states) when `CRYPTO_ANALYZER_ENABLE_REGIMES=1`.

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                     PROVIDER LAYER (pluggable)                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐                    │
│  │   Coinbase   │  │    Kraken     │  │   Dexscreener      │   + your own...    │
│  │ SpotProvider │  │ SpotProvider  │  │  DexProvider      │                    │
│  └──────┬───────┘  └──────┬───────┘  └────────┬───────────┘                    │
│         │                 │                    │                                │
│  ┌──────▼─────────────────▼────────────────────▼──────────┐                  │
│  │         Provider Chain (retry, circuit breaker, LKG)     │                  │
│  └──────────────────────┬─────────────────────────────────┘                  │
└─────────────────────────┼──────────────────────────────────────────────────────┘
                          │
                          ▼  ingest.get_poll_context() → run_migrations → chains
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         DATABASE LAYER (SQLite)                                 │
│  spot_price_snapshots │ sol_monitor_snapshots │ provider_health │ universe_*     │
│  bars_5min .. bars_1D (OHLCV, idempotent)                                       │
│  factor_model_runs, factor_betas, residual_returns (v2 migrations)             │
│  regime_runs, regime_states (Phase 3, optional when ENABLE_REGIMES=1)           │
└─────────────────────────────────────────────────────────────────────────────────┘
                          │
                          ▼  materialize bars │ factor_materialize │ regime_materialize (opt)
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       RESEARCH PIPELINE                                         │
│  Factor model (OLS) → Signal validation (IC, orth) → Portfolio (QP) → Walk-fwd   │
│  Regime (legacy classify + optional RegimeDetector) │ Overfitting │ Experiments │
│  Governance (manifests, dataset_id, integrity)                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Streamlit (12 pages) │ FastAPI (read-only) │ CLI (poll, reportv2, null_suite…)  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Design principles:**
- **Single source of truth:** All analytics consume the same SQLite database. Bar and factor materialization are deterministic and idempotent.
- **Ingest / read_api boundary:** Poll uses `crypto_analyzer.ingest` (DB writes, migrations, provider chains). Dashboard uses `read_api` for health and allowlist; no direct db imports in CLI/UI.
- **Provider-agnostic ingestion:** Data sources are pluggable. Swap Coinbase for Binance by implementing one class.
- **Versioned migrations:** Core + v2 (factor tables) applied by `run_migrations`; Phase 3 (regime tables) only when regimes are enabled.
- **Reproducibility:** Every run records a manifest with git commit, environment, data window, and output hashes.

---

## Getting Started

### Prerequisites

- Python 3.10+
- No API keys required (all data sources are public endpoints)

### Installation

```bash
git clone https://github.com/AlpharomeroJL/Crypto-Anaylzer.git && cd Crypto-Anaylzer
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### Quick Demo

One command runs the full pipeline: preflight checks, data collection, bar materialization, research report, and experiment recording.

```powershell
.\scripts\run.ps1 demo
```

### Step-by-Step

```bash
# 1. Verify installation and environment
.\scripts\run.ps1 doctor

# 2. Collect data (auto-discovers top DEX pairs on Solana)
.\scripts\run.ps1 universe-poll --universe --universe-chain solana --interval 60

# 3. Build OHLCV bars from raw snapshots
.\scripts\run.ps1 materialize --freq 1h

# 4. Generate research report with overfitting controls
.\scripts\run.ps1 reportv2 --freq 1h --out-dir reports --hypothesis "baseline momentum"

# 5. Launch interactive dashboard
.\scripts\run.ps1 streamlit
```

---

## How It Works

### Data Ingestion

The poller uses **`crypto_analyzer.ingest`**: `get_poll_context(db_path)` opens the DB, runs **run_migrations** (core + v2 factor tables), and builds the spot and DEX provider chains. Each cycle writes to `spot_price_snapshots`, `sol_monitor_snapshots`, and (in universe mode) `universe_allowlist` / `universe_churn_log`. Provider health is stored in `provider_health`. Resilience: retry/backoff, circuit breakers, last-known-good cache, data quality gates.

### Materialization

- **Bars:** Raw snapshots → deterministic OHLCV bars (5min, 15min, 1h, 1D). Idempotent; log returns, cumulative returns, rolling volatility.
- **Factors (v2):** `factor_materialize` writes `factor_model_runs`, `factor_betas`, `residual_returns` (causal rolling OLS, dataset_id, run_id). Used by reportv2 and research pipeline.
- **Regimes (Phase 3, optional):** When `CRYPTO_ANALYZER_ENABLE_REGIMES=1`, run **run_migrations_phase3** then `regime_materialize` to fill `regime_runs` / `regime_states`. reportv2 supports `--regimes REGIME_RUN_ID` for regime-conditioned summaries.

### Research Pipeline

1. **Factor decomposition** — Rolling OLS (BTC/ETH) → idiosyncratic residuals; BTC-only fallback when ETH missing.
2. **Cross-sectional factors** — Size, volume, momentum per timestamp; winsorized z-scores.
3. **Signal validation** — IC, IC decay, orthogonalization.
4. **Portfolio construction** — Constrained QP (scipy SLSQP), rank-based fallback.
5. **Walk-forward backtesting** — Strict train/test split, no lookahead.
6. **Overfitting controls** — Deflated Sharpe, PBO proxy, block bootstrap, multiple-testing adjustment (e.g. BH).
7. **Regime detection** — Legacy: classify regime (risk-off, dispersion, beta compression, chop). Optional Phase 3: RegimeDetector (fit/predict), regime-conditioned IC in reportv2.

### Dashboard

Streamlit (12 pages): Overview, Pair detail, Scanner, Backtest, Walk-Forward, Market Structure, Signals, Research, Institutional Research, Experiments, Runtime/Health, Governance. Uses **read_api** for allowlist and health; **ingest.get_provider_health** for provider status.

---

## Data Flow

```
  Public APIs (Coinbase, Kraken, Dexscreener)
           │
           ▼  ingest.get_poll_context() → SpotPriceChain, DexSnapshotChain
  spot_price_snapshots, sol_monitor_snapshots, universe_allowlist, provider_health
           │
           ▼  materialize (cli/materialize.py)   factor_materialize (optional)
  bars_{freq}   │   factor_model_runs, factor_betas, residual_returns
           │    │   regime_runs, regime_states (Phase 3, optional)
           └────┴──► Research pipeline (data.py, factors, alpha_research, reportv2)
                          │
                          ▼  experiments.db, reports/*.json, manifests
```

---

## Extending Providers

The provider architecture is designed for extensibility. To add a new exchange:

### Example: Adding a Binance Spot Provider

```python
# crypto_analyzer/providers/cex/binance.py
"""Binance spot price provider (public API, no authentication)."""
from __future__ import annotations
from datetime import datetime, timezone
import requests
from ..base import SpotQuote

class BinanceSpotProvider:
    """Fetch spot prices from the Binance public API."""

    @property
    def provider_name(self) -> str:
        return "binance"

    def get_spot(self, symbol: str) -> SpotQuote:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        resp = requests.get(url, timeout=15.0)
        resp.raise_for_status()
        price = float(resp.json()["price"])
        return SpotQuote(
            symbol=symbol.upper(),
            price_usd=price,
            provider_name=self.provider_name,
            fetched_at_utc=ts,
        )
```

Then register it in `crypto_analyzer/providers/defaults.py` and add to `config.yaml` under `providers.spot_priority`. The provider chain handles resilience. For DEX providers, implement `DexSnapshotProvider` (`get_snapshot()`, `search_pairs()`); see `crypto_analyzer/providers/dex/dexscreener.py`.

---

## Project Structure

```
├── config.yaml                      # Database, universe, provider, and filter settings
├── pyproject.toml                   # Package metadata and dependencies
├── requirements.txt                 # Pinned dependencies for reproducibility
│
├── crypto_analyzer/                  # Core library
│   ├── ingest/                       # Poll context, run_migrations, provider chains (CLI uses this)
│   │   └── __init__.py               #   get_poll_context, run_one_cycle
│   ├── read_api.py                   # Read-only API: health, allowlist (dashboard uses this)
│   ├── providers/                    # Extensible provider architecture
│   │   ├── base.py                   #   SpotPriceProvider, DexSnapshotProvider, SpotQuote
│   │   ├── registry.py, chain.py     #   Registry and ordered fallback chains
│   │   ├── resilience.py             #   Circuit breaker, retry/backoff, LKG cache
│   │   ├── defaults.py               #   Default registry and config loader
│   │   ├── cex/                       #   Coinbase, Kraken
│   │   └── dex/                       #   Dexscreener
│   │
│   ├── db/                           # Database layer
│   │   ├── migrations.py             #   Core migrations; calls run_migrations_v2
│   │   ├── migrations_v2.py          #   factor_model_runs, factor_betas, residual_returns
│   │   ├── migrations_phase3.py      #   regime_runs, regime_states (opt-in only)
│   │   ├── writer.py                 #   Shared write layer with provenance
│   │   └── health.py                 #   Provider health persistence
│   │
│   ├── config.py, data.py            # Configuration and data loading
│   ├── features.py                   # Returns, vol, drawdown, momentum, beta, dispersion
│   ├── factors.py                    # Multi-factor OLS, rolling regression, causal residuals
│   ├── factor_materialize.py         # Materialize factor runs/betas/residuals to DB
│   ├── cs_factors.py, cs_model.py    # Cross-sectional factors and signal combiner
│   ├── optimizer.py                  # Constrained QP (scipy SLSQP)
│   ├── signals.py, signals_xs.py     # Signal detection, journal, orthogonalization
│   ├── portfolio.py, portfolio_advanced.py  # Vol targeting, beta neutral, capacity filters
│   ├── execution_cost.py             # Fees, slippage, capacity curve (unified cost model)
│   ├── risk_model.py                 # Covariance (EWMA, Ledoit-Wolf)
│   ├── regimes/                      # Regime classification and Phase 3 detector/materialize
│   │   ├── __init__.py               #   Legacy classify + optional RegimeDetector API
│   │   ├── legacy.py                 #   classify_market_regime, explain_regime
│   │   ├── regime_detector.py        #   RegimeDetector (fit/predict), filter-only in test
│   │   ├── regime_features.py        #   Causal regime features
│   │   ├── regime_materialize.py     #   regime_runs, regime_states
│   │   └── _flags.py                 #   is_regimes_enabled (ENABLE_REGIMES)
│   ├── walkforward.py                # Walk-forward train/test split engine
│   ├── alpha_research.py             # IC, decay, signal builders
│   ├── statistics.py                 # Block bootstrap, confidence intervals
│   ├── multiple_testing.py           # Deflated Sharpe, PBO proxy
│   ├── multiple_testing_adjuster.py  # BH/BY family adjustment
│   ├── evaluation.py                 # Regime-conditioned performance
│   ├── research_universe.py          # Universe builder with quality filters
│   ├── experiments.py, experiment_store.py  # SQLite/Postgres experiment registry
│   ├── governance.py, artifacts.py    # Run manifests, SHA256, dataset fingerprinting
│   ├── integrity.py, diagnostics.py  # Data quality, health scoring
│   ├── dataset.py, timeutils.py      # Dataset fingerprinting, time helpers
│   ├── validation_bundle.py          # Per-signal validation bundle (reportv2)
│   ├── order_intent.py               # Execution boundary (no live orders)
│   ├── doctor.py                     # Preflight system checks
│   ├── null_suite.py                 # Null/placebo runner (random ranks, permute, block shuffle)
│   └── spec.py                       # Research spec, research-only boundary validation
│
├── cli/                              # Command-line entry points
│   ├── poll.py                       # Data ingestion (uses ingest API)
│   ├── materialize.py                # OHLCV bar builder
│   ├── app.py                        # Streamlit dashboard (12 pages)
│   ├── scan.py                       # Opportunity scanner
│   ├── research_report.py            # Research report (v1)
│   ├── research_report_v2.py          # Advanced report (IC, PBO, QP, regimes optional)
│   ├── report_daily.py               # Daily market structure report
│   ├── backtest.py, backtest_walkforward.py
│   ├── api.py                        # FastAPI read-only research API
│   ├── null_suite.py                 # Null suite CLI
│   └── demo.py                       # One-command demo
│
├── tests/                            # Pytest suite (mocked HTTP, no live network)
├── docs/                             # Design, architecture, spec, diagrams
├── tools/                            # e.g. check_dataset
└── scripts/                          # run.ps1 (doctor, poll, materialize, reportv2, verify, …)
```

---

## Testing

```bash
# Run full test suite
.\scripts\run.ps1 test
# Or: python -m pytest -q

# Full verification (doctor → pytest → ruff → research-only → diagrams)
.\scripts\run.ps1 verify
```

The test suite covers: provider chain (fallback, circuit breaker, retry, LKG), data quality gates, DB provenance, migrations (core, v2, phase3), factor and regime materialization, reportv2 (including optional regimes), null suite, experiment registry, API smoke tests, governance and integrity. No tests make live network calls; all HTTP is mocked.

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `doctor` | Preflight: environment, dependencies, DB schema, pipeline smoke test |
| `poll` | Single-pair data poll (provider-based with fallback) |
| `universe-poll --universe ...` | Multi-asset universe discovery with churn controls |
| `materialize` | Build deterministic OHLCV bars (5min, 15min, 1h, 1D) |
| `analyze` | Legacy single-pair analysis (momentum, vol) |
| `scan` | Multi-mode scanner (momentum, residual, vol breakout, mean reversion) |
| `report` | Research report (v1, single-factor) |
| `reportv2` | Research report with IC, orthogonalization, PBO, QP, experiment logging; optional `--regimes` when ENABLE_REGIMES=1 |
| `daily` | Daily market structure report |
| `backtest` | Single-asset backtest (trend following, volatility breakout) |
| `walkforward` | Walk-forward backtest with out-of-sample fold stitching |
| `streamlit` | Interactive dashboard (12 pages including provider health) |
| `api` | Local read-only research API (FastAPI) |
| `demo` | One-command demo: doctor → poll → materialize → report |
| `null_suite` | Null/placebo artifact runner (random ranks, permuted signal, block shuffle) |
| `verify` | Full check: doctor → pytest → ruff → research-only boundary → diagrams |
| `test` | Run pytest |
| `check-dataset` | Inspect dataset fingerprints and row counts |

All commands: `.\scripts\run.ps1 <command> [args...]`

---

## Technology Stack

| Layer | Technology |
|-------|------------|
| **Core** | Python 3.10+, pandas, NumPy, SciPy |
| **Storage** | SQLite (single file); optional Postgres for experiment backend |
| **Ingestion** | ingest API + provider chains (circuit breakers, retry/backoff) |
| **Data sources** | Coinbase, Kraken, Dexscreener (public, no API keys) |
| **Visualization** | Streamlit (12-page dashboard), Plotly, Matplotlib |
| **API** | FastAPI + Uvicorn (optional `[api]` extra) |
| **Statistics** | SciPy (QP), scikit-learn (Ledoit-Wolf, optional) |
| **Testing** | pytest (mocked HTTP, no live network); `verify` for full gate |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No data in dashboard | Run `.\scripts\run.ps1 poll` (or universe-poll) then `.\scripts\run.ps1 materialize` |
| Bars table not found | Run `.\scripts\run.ps1 materialize --freq 1h` |
| PyYAML not installed | `pip install PyYAML` (config falls back to defaults without it) |
| Provider shows DOWN | Circuit breaker; auto-recovers after cooldown |
| Need >= 3 assets in Research | Universe mode needs several poll cycles; wait or add pairs in config.yaml |
| reportv2 --regimes fails | Set `CRYPTO_ANALYZER_ENABLE_REGIMES=1` and run Phase 3 migrations before regime materialize |
| Test failures | Run `.\scripts\run.ps1 doctor`; ensure venv is active |
| Dashboard won't start | `pip install streamlit`, run from repo root |

---

## Documentation

| Document | Contents |
|----------|----------|
| [Design & Architecture](docs/design.md) | Data flow, provider contracts, failure modes |
| [Contributing](CONTRIBUTING.md) | Dev setup, testing, style, adding providers, verify |
| [Architecture](docs/architecture.md) | Module responsibility matrix |
| [Deployment](docs/deployment.md) | Windows service setup for 24/7 operation |
| [Institutional Principles](docs/institutional.md) | Research standards and validation methodology |
| [Private Conversion Plan](docs/private_conversion.md) | Using OSS as dependency for a private execution layer |
| [Spec / Implementation Ledger](docs/spec/implementation_ledger.md) | Spec requirements and phase status |

### Architecture Diagrams

Diagrams live in `docs/diagrams/` (PlantUML). See [diagram index](docs/diagrams/README.md). Regenerate SVG/PNG:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\export_diagrams.ps1
```

---

<details>
<summary><strong>Engineering Decisions</strong></summary>

| Decision | Rationale |
|----------|-----------|
| **SQLite over Postgres** | Zero-config, single-file portability for research-scale data. |
| **Ingest + read_api** | Clear boundary: poll owns writes and migrations; dashboard reads via read_api only. |
| **Versioned migrations** | Core + v2 applied together; Phase 3 (regimes) opt-in so default DB stays minimal. |
| **Provider chain pattern** | Config-driven fallback, circuit breakers, resilience without coupling to exchanges. |
| **Log returns throughout** | Additive, symmetric, correct for multi-period aggregation. |
| **OLS for factor decomposition** | Residuals with zero factor exposure by construction. |
| **Walk-forward over k-fold** | Time series requires temporal separation; no lookahead. |
| **Spearman rank IC** | Robust to fat-tailed crypto returns. |
| **Block bootstrap** | Preserves serial correlation; i.i.d. bootstrap overstates confidence. |
| **Circuit breaker per provider** | Avoids thundering herd on failing endpoints; auto-recovery. |

</details>

---

## License

MIT License. See [LICENSE](LICENSE).
