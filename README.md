# Crypto Quantitative Research Platform

A local-first quantitative research engine for cryptocurrency markets. It ingests live data from decentralized and centralized exchanges, normalizes it into a single SQLite database, and runs institutional-grade statistical analysis — factor decomposition, cross-sectional signal validation, portfolio optimization, and walk-forward backtesting — all without API keys, cloud services, or trading execution.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-200%20passed-brightgreen.svg)](#testing)

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

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                           PROVIDER LAYER (pluggable)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐                   │
│  │   Coinbase    │  │    Kraken    │  │   Dexscreener     │   + your own...   │
│  │  SpotProvider │  │ SpotProvider │  │  DexProvider      │                   │
│  └──────┬───────┘  └──────┬───────┘  └────────┬──────────┘                   │
│         │                 │                    │                              │
│  ┌──────▼─────────────────▼────────────────────▼──────────┐                  │
│  │              Provider Chain (ordered fallback)          │                  │
│  │   Circuit Breaker → Retry/Backoff → Quality Gate       │                  │
│  │              → Last-Known-Good Cache                    │                  │
│  └──────────────────────┬─────────────────────────────────┘                  │
└─────────────────────────┼──────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         DATABASE LAYER (SQLite)                                │
│  ┌──────────────────┐  ┌────────────────────┐  ┌────────────────┐             │
│  │ spot_price_      │  │ sol_monitor_       │  │ provider_      │             │
│  │ snapshots        │  │ snapshots          │  │ health         │             │
│  │ + provider_name  │  │ + provider_name    │  │                │             │
│  │ + fetch_status   │  │ + fetch_status     │  │                │             │
│  └────────┬─────────┘  └─────────┬──────────┘  └────────────────┘             │
│           └──────────┬───────────┘                                            │
│                      ▼                                                        │
│           ┌──────────────────┐                                                │
│           │  bars_1h / _1D   │  (materialized OHLCV, idempotent)              │
│           └────────┬─────────┘                                                │
└────────────────────┼────────────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       RESEARCH PIPELINE                                        │
│  ┌────────────┐  ┌────────────┐  ┌───────────┐  ┌────────────┐               │
│  │  Factor    │  │  Signal    │  │ Portfolio  │  │ Walk-Fwd   │               │
│  │  Model     │→ │ Validation │→ │ Optimizer  │→ │ Backtest   │               │
│  │ (OLS beta) │  │ (IC, orth) │  │  (QP/L-S)  │  │ (no leak)  │               │
│  └────────────┘  └────────────┘  └───────────┘  └────────────┘               │
│                                                                               │
│  ┌────────────┐  ┌────────────┐  ┌───────────┐  ┌────────────┐               │
│  │  Regime    │  │ Overfitting│  │ Experiment │  │ Governance  │               │
│  │ Detection  │  │  Controls  │  │  Registry  │  │ (manifests) │               │
│  └────────────┘  └────────────┘  └───────────┘  └────────────┘               │
└─────────────────────────────────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  PRESENTATION: Streamlit Dashboard (12 pages) │ FastAPI (read-only) │ CLI      │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Design principles:**
- **Single source of truth:** All analytics consume the same SQLite database. Bar construction is deterministic and idempotent.
- **Provider-agnostic ingestion:** Data sources are pluggable. Swap Coinbase for Binance by implementing one class.
- **Separation of concerns:** Ingestion, materialization, modeling, and visualization are independent stages.
- **Reproducibility:** Every run records a manifest with git commit, environment, data window, and output hashes.

---

## Getting Started

### Prerequisites

- Python 3.10+
- No API keys required (all data sources are public endpoints)

### Installation

```bash
git clone <repo-url> && cd crypto-analyzer
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

The poller runs every 60 seconds and collects two types of data through the **provider chain**:

1. **DEX pair snapshots** — Price, liquidity, volume, and transaction counts from Dexscreener for the configured universe of trading pairs.
2. **Spot reference prices** — BTC, ETH, and SOL USD prices from Coinbase (primary) with automatic Kraken fallback.

Each provider call is wrapped in a resilience layer:
- **Retry with exponential backoff** for transient failures (429, timeouts)
- **Circuit breakers** that skip providers known to be failing (auto-recovery after cooldown)
- **Last-known-good cache** that prevents data gaps during brief outages
- **Data quality gates** that reject invalid or stale quotes before they reach the database

Every record includes **provenance metadata**: which provider served it, when it was fetched, and whether it was a primary or fallback response.

### Materialization

Raw snapshots are aggregated into deterministic OHLCV bars at four frequencies (5min, 15min, 1h, 1D). The process is idempotent — rerunning on the same data always produces identical bars with computed log returns, cumulative returns, and rolling volatility.

### Research Pipeline

1. **Factor decomposition** — Rolling OLS regression decomposes each asset's returns into BTC/ETH factor exposure and an idiosyncratic residual. Falls back gracefully to BTC-only when ETH data is unavailable.
2. **Cross-sectional factors** — Size (log liquidity), volume, and momentum factors are computed per timestamp with winsorized z-scores.
3. **Signal validation** — Information Coefficient (Spearman rank correlation vs. future returns), IC decay analysis, and signal orthogonalization via sequential OLS residualization.
4. **Portfolio construction** — Constrained QP optimizer (scipy SLSQP) with dollar-neutral, beta-neutral, and max-weight constraints. Rank-based fallback on optimizer failure.
5. **Walk-forward backtesting** — Strict rolling train/test splits with no lookahead. Out-of-sample folds are stitched for aggregate performance.
6. **Overfitting controls** — Deflated Sharpe ratio, PBO proxy, block bootstrap confidence intervals, and multiple testing warnings.
7. **Regime detection** — Market conditions (risk-off, high dispersion, beta compression, chop) are classified and performance is broken down by regime.

### Dashboard

The Streamlit dashboard provides 12 interactive pages: overview leaderboard, pair detail charts, multi-mode scanner, single-asset backtester, walk-forward analysis, market structure (correlation, beta, dispersion), signal journal, cross-sectional research (IC, decay, portfolio), institutional research (orthogonalization, advanced portfolio, overfitting defenses), experiment registry with comparison, runtime health with provider status, and governance (manifests, data integrity).

---

## Data Flow

```
  Public APIs                SQLite (single file)              Analytics
  ──────────                 ────────────────────              ─────────

  Coinbase ──┐
  Kraken  ───┤ SpotPriceChain ──► spot_price_snapshots ──┐
             │  (fallback)        (+ provider_name,       │
             │                     fetched_at, status)     │
             │                                             ├──► bars_{freq}
  Dexscreener─┤ DexSnapshotChain ► sol_monitor_snapshots──┘    (OHLCV, idempotent)
              │  (circuit breaker)  (+ provider_name,               │
              │                      fetched_at, status)            │
              │                                                     ▼
              │                                              Research pipeline
              │                                              (factors, signals,
              │                                               portfolio, backtest)
              │                                                     │
              │                    provider_health ◄─────────────────┤ (health tracking)
              │                    experiments.db  ◄─────────────────┤ (experiment registry)
              │                    reports/*.json  ◄─────────────────┘ (governance manifests)
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
from ..base import ProviderStatus, SpotQuote

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

Then register it:

```python
# In crypto_analyzer/providers/defaults.py
from .cex.binance import BinanceSpotProvider

def create_default_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register_spot("coinbase", CoinbaseSpotProvider)
    registry.register_spot("kraken", KrakenSpotProvider)
    registry.register_spot("binance", BinanceSpotProvider)  # new
    ...
```

And add it to `config.yaml`:

```yaml
providers:
  spot_priority: ["coinbase", "binance", "kraken"]
```

The provider chain handles all resilience (retry, circuit breaker, fallback) automatically. No changes needed in the polling loop, dashboard, or models.

For DEX providers, implement the `DexSnapshotProvider` protocol with `get_snapshot()` and `search_pairs()` methods. See `crypto_analyzer/providers/dex/dexscreener.py` for the reference implementation.

---

## Project Structure

```
├── config.yaml                      # Database, universe, provider, and filter settings
├── pyproject.toml                   # Package metadata and dependencies
├── requirements.txt                 # Pinned dependencies for reproducibility
│
├── crypto_analyzer/                 # Core library
│   ├── providers/                   # Extensible provider architecture
│   │   ├── base.py                  #   Protocol interfaces (SpotPriceProvider, DexSnapshotProvider)
│   │   ├── registry.py              #   Provider registry and factory
│   │   ├── chain.py                 #   Ordered fallback chains with resilience
│   │   ├── resilience.py            #   Circuit breaker, retry/backoff, LKG cache
│   │   ├── defaults.py              #   Default registry and config loader
│   │   ├── cex/                     #   CEX spot providers
│   │   │   ├── coinbase.py          #     Coinbase public API
│   │   │   └── kraken.py            #     Kraken public API
│   │   └── dex/                     #   DEX snapshot providers
│   │       └── dexscreener.py       #     Dexscreener public API
│   │
│   ├── db/                          # Database layer
│   │   ├── migrations.py            #   Idempotent schema migrations
│   │   ├── writer.py                #   Shared write layer with provenance
│   │   └── health.py                #   Provider health persistence
│   │
│   ├── config.py                    # Configuration loader (YAML + env overrides)
│   ├── data.py                      # Data loading (snapshots, bars, spot prices)
│   ├── features.py                  # Returns, volatility, drawdown, momentum, beta
│   ├── factors.py                   # Multi-factor OLS (BTC/ETH), rolling regression
│   ├── cs_factors.py                # Cross-sectional factor construction
│   ├── cs_model.py                  # Cross-sectional signal combiner
│   ├── optimizer.py                 # Constrained QP optimizer (scipy SLSQP)
│   ├── signals.py                   # Signal detection and journal
│   ├── signals_xs.py                # Cross-sectional z-score, orthogonalization
│   ├── portfolio.py                 # Vol targeting, risk parity, beta neutralization
│   ├── portfolio_advanced.py        # Constrained optimization with capacity filters
│   ├── risk_model.py                # Covariance estimation (EWMA, Ledoit-Wolf)
│   ├── regimes.py                   # Market regime classification
│   ├── walkforward.py               # Walk-forward train/test split engine
│   ├── alpha_research.py            # IC, signal builders, decay analysis
│   ├── statistics.py                # Block bootstrap and confidence intervals
│   ├── multiple_testing.py          # Deflated Sharpe, PBO proxy
│   ├── evaluation.py                # Regime-conditioned performance
│   ├── research_universe.py         # Universe builder with quality filters
│   ├── experiments.py               # SQLite experiment registry
│   ├── experiment_store.py          # Pluggable store (SQLite/Postgres)
│   ├── governance.py                # Run manifests, git tracking
│   ├── integrity.py                 # Data quality checks
│   ├── artifacts.py                 # Artifact I/O and SHA256 hashing
│   ├── diagnostics.py               # Stability, fragility, health scoring
│   ├── dataset.py                   # Dataset fingerprinting (dataset_id)
│   ├── doctor.py                    # Preflight system checks
│   └── spec.py                      # Research spec versioning
│
├── cli/                             # Command-line entry points
│   ├── poll.py                      #   Data ingestion (provider-based)
│   ├── app.py                       #   Streamlit dashboard (12 pages)
│   ├── materialize.py               #   OHLCV bar builder
│   ├── scan.py                      #   Opportunity scanner
│   ├── research_report_v2.py        #   Advanced research report
│   ├── backtest.py                  #   Single-asset backtester
│   ├── backtest_walkforward.py      #   Walk-forward backtester
│   ├── report_daily.py              #   Daily market structure report
│   ├── api.py                       #   FastAPI research API
│   └── demo.py                      #   One-command demo
│
├── tests/                           # 200 tests (pytest)
├── docs/                            # Design docs and guides
├── tools/                           # Utility scripts
└── scripts/                         # PowerShell runners
```

---

## Testing

```bash
# Run all tests
.\scripts\run.ps1 test

# Or directly
python -m pytest -q
```

**200 tests** across 33 suites covering:

- **Provider chain:** Fallback logic, circuit breaker trip/recovery, retry/backoff, last-known-good caching
- **Data quality gates:** Invalid price rejection, degraded state handling
- **Database provenance:** Provider name, fetch status, and error tracking per record
- **Migrations:** Idempotent schema creation, column additions
- **Integration:** Full poll cycle with mocked HTTP to a temp SQLite DB
- **Core analytics:** Return computation, multi-factor OLS, cross-sectional factors, QP optimizer, walk-forward splits, bootstrap statistics, regime classification
- **Experiment registry:** SQLite metadata, tagging, hypothesis filtering
- **API:** REST endpoint smoke tests
- **Governance:** Manifest generation, dataset fingerprinting, integrity checks

No tests make live network calls. All HTTP interactions are mocked.

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `doctor` | Preflight checks: environment, dependencies, DB schema, pipeline smoke test |
| `poll` | Single-pair data poller (provider-based with fallback) |
| `universe-poll --universe ...` | Multi-asset universe discovery with churn controls |
| `materialize` | Build deterministic OHLCV bars (5min, 15min, 1h, 1D) |
| `scan` | Multi-mode scanner (momentum, residual, vol breakout, mean reversion) |
| `reportv2` | Research report with IC, orthogonalization, PBO, QP, experiment logging |
| `backtest` | Single-asset backtest (trend following, volatility breakout) |
| `walkforward` | Walk-forward backtest with out-of-sample fold stitching |
| `streamlit` | Interactive dashboard (12 pages including provider health) |
| `api` | Local read-only research API (FastAPI) |
| `demo` | One-command demo: doctor → poll → materialize → report |

All commands: `.\scripts\run.ps1 <command> [args...]`

---

## Technology Stack

| Layer | Technology |
|-------|------------|
| **Core** | Python 3.10+, pandas, NumPy, SciPy |
| **Storage** | SQLite (single file), optional Postgres for experiment backend |
| **Ingestion** | Provider/plugin architecture with circuit breakers and retry/backoff |
| **Data Sources** | Coinbase, Kraken, Dexscreener (all public, no API keys) |
| **Visualization** | Streamlit (12-page dashboard), Plotly, Matplotlib |
| **API** | FastAPI + Uvicorn (optional `[api]` extra) |
| **Statistics** | SciPy (QP optimizer), scikit-learn (Ledoit-Wolf, optional) |
| **Testing** | pytest (200 tests, mocked HTTP, no live network) |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `No data` in dashboard | Run `.\scripts\run.ps1 poll` for a few minutes first, then `.\scripts\run.ps1 materialize` |
| `Bars table not found` | Run `.\scripts\run.ps1 materialize --freq 1h` to build bars from snapshots |
| `PyYAML not installed` | `pip install PyYAML` — config.py falls back to defaults without it |
| Provider shows `DOWN` | Circuit breaker opened after repeated failures; it auto-recovers after 60s cooldown |
| `Need >= 3 assets` in Research | Universe mode needs a few poll cycles to discover enough pairs; wait or add pairs to config.yaml |
| Test failures | Run `.\scripts\run.ps1 doctor` for diagnostics; ensure you're in the venv |
| Dashboard won't start | `pip install streamlit` and run from the repo root directory |

---

## Documentation

| Document | Contents |
|----------|----------|
| [Design & Architecture](docs/design.md) | Data flow, provider contracts, failure modes, design decisions |
| [Contributing](CONTRIBUTING.md) | Dev setup, testing, style guide, adding providers |
| [Architecture](docs/architecture.md) | Module responsibility matrix |
| [Deployment](docs/deployment.md) | Windows service setup for 24/7 operation |
| [Institutional Principles](docs/institutional.md) | Research standards and validation methodology |

---

<details>
<summary><strong>Engineering Decisions</strong></summary>

| Decision | Rationale |
|----------|-----------|
| **SQLite over Postgres** | Zero-config, single-file portability. Research-scale data (millions of rows) doesn't need a server. |
| **Provider chain pattern** | Config-driven fallback order, circuit breakers, and resilience wrappers keep ingestion robust without coupling to specific exchanges. |
| **Log returns throughout** | Additive across time, symmetric, mathematically correct for multi-period aggregation. |
| **OLS for factor decomposition** | Produces residuals with exactly zero factor exposure by construction. |
| **Walk-forward over k-fold** | Time series autocorrelation requires temporal separation; walk-forward prevents lookahead bias. |
| **Spearman rank IC** | Robust to fat-tailed distributions ubiquitous in crypto. |
| **Block bootstrap** | Preserves serial correlation in financial returns. i.i.d. bootstrap gives overconfident intervals. |
| **Frozen dataclasses for provider contracts** | Immutability prevents accidental mutation, type safety at boundaries. |
| **Circuit breaker per provider** | Prevents thundering herd on a failing endpoint; auto-recovers after cooldown. |

</details>

---

## License

MIT License. See [LICENSE](LICENSE).
