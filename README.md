# Crypto-Analyzer

Systematic digital-asset research platform for factor modeling, regime detection, and robust validation.

**Research-only system.**  
No execution. No trading keys. No broker/exchange connectivity. No order routing.

---

## 1. System Overview

Crypto-Analyzer is a cross-asset quantitative research engine built on:

- DEX snapshot ingestion
- Deterministic bar materialization
- Factor modeling (BTC/ETH beta + residuals)
- Cross-sectional signal validation
- Portfolio research with cost modeling
- Governance and reproducibility controls

It is designed to operate under institutional research constraints: auditability, stability, and statistical discipline.

---

## 2. High-Level Architecture

```
            +----------------------+
            |  dex_poll_to_sqlite  |
            |  (snapshot ingestion)|
            +----------+-----------+
                       |
                       v
            +----------------------+
            |     SQLite DB        |
            |  snapshots + bars    |
            +----------+-----------+
                       |
         +-------------+--------------+
         |                            |
         v                            v
+------------------+        +--------------------+
| materialize_bars |        | data / features    |
| (5m/1h/1D OHLC)  |        | returns, vol, DD   |
+------------------+        +--------------------+
         |                            |
         +------------+---------------+
                      |
                      v
    +-----------------+----------------------+
    | Research / Backtests / Reports / UI    |
    | scan • backtest • walkforward • v2     |
    +----------------------------------------+
```

- **Single source of truth:** `dex_data.sqlite`.
- All analytics consume the same normalized bars and factor series.

---

## 3. Data Flow

**Ingestion** — `dex_poll_to_sqlite.py` polls DEX + spot data into SQLite.

**Materialization** — `materialize_bars.py` builds deterministic OHLC bars (5min, 15min, 1h, 1D).

**Feature Computation** — `features.py` computes:

- Log returns
- Annualized volatility
- Sharpe (bar-scaled)
- Drawdown

**Downstream Modules**

- `dex_analyze.py`
- `dex_scan.py`
- `backtest.py`
- `backtest_walkforward.py`
- `research_report.py`
- `research_report_v2.py`
- `app.py` (Streamlit)

All modules use the same DB and configuration layer.

---

## 4. Core Research Modules

### 4.1 Factor Modeling

- BTC beta and correlation
- Residual returns
- Beta compression detection

### 4.2 Regime Classification

- Volatility regime
- Dispersion regime
- Beta state (macro_beta, dispersion, chop, risk_off)

### 4.3 Signals

- Momentum
- Residual momentum
- Dispersion extremes
- Beta compression

Signals are research signals only — no execution.

### 4.4 Cross-Sectional Research

- Spearman IC
- IC decay
- Turnover
- Regime-conditioned IC

### 4.5 Portfolio Research

- Vol targeting
- Risk parity
- Beta neutrality
- Long/short construction
- Cost modeling (fee + slippage proxy)

### 4.6 Overfitting Controls

- Walk-forward validation
- Block bootstrap
- Deflated Sharpe
- PBO proxy
- Experiment logging

---

## 5. Validation Framework

- Strict no-lookahead
- Walk-forward train/test separation
- Frequency-consistent annualization
- Optional strict integrity checks (`--strict-integrity`)
- Statistical robustness tools (bootstrap, DSR, PBO)

Default mode is warn-only. Strict mode is opt-in.

---

## 6. Running the System

Use the helper script to ensure venv isolation:

```powershell
.\scripts\run.ps1 <command>
```

**Available commands:** `poll`, `universe-poll`, `materialize`, `report`, `reportv2`, `streamlit`, `doctor`, `test`.

### 6.1 Quick Start (Multi-Asset)

```powershell
.\scripts\run.ps1 doctor
.\scripts\run.ps1 universe-poll --universe --universe-chain solana --interval 60 --universe-debug 5
```

Confirm logs show:

- `Dex pairs: X (universe_mode=True)`
- `Universe refreshed: N pairs`

If `universe_mode=False`, you did not pass `--universe`.

### 6.2 Materialize Bars

```powershell
.\scripts\run.ps1 materialize --freq 1h
```

### 6.3 Generate Research Report

```powershell
.\scripts\run.ps1 reportv2 --freq 1h --out-dir reports --save-charts
```

Optional strict integrity:

```powershell
.\scripts\run.ps1 reportv2 --strict-integrity --strict-integrity-pct 1
```

---

## 7. Universe Mode (Multi-Asset)

Universe discovery uses Dexscreener public search endpoints.

### 7.1 Discovery Logic

- Multi-query search (chain defaults)
- Merge + de-duplicate by pair address
- Deterministic ranking: Liquidity DESC, Volume DESC, Label ASC, Address ASC

### 7.2 Quality Filters

- Require liquidity and 24h volume
- Reject base == quote
- Reject stable/stable
- Restrict quote to allowlist (default: USDC/USDT)

### 7.3 Stability Controls

- `max_churn_pct` (default 0.20)
- `min_persistence_refreshes` (default 2)

### 7.4 Audit Tables

- `universe_allowlist`
- `universe_churn_log`
- `universe_persistence`

**Verify via:**

```powershell
python check_universe.py
```

**Stable system characteristics:**

- 3+ allowlist refresh timestamps
- Stable N per refresh
- Minimal churn (0–1 add/remove typical)

---

## 8. Streamlit Interface

```powershell
.\scripts\run.ps1 streamlit
```

**Pages:** Overview, Scanner, Backtest, Walk-Forward, Market Structure, Signals, Research, Institutional Research, Runtime / Health, Governance.

UI degrades gracefully when asset count &lt; 3.

---

## 9. Reports & Artifacts

Reports write to:

```
reports/
 ├── csv/
 ├── charts/
 ├── manifests/
 └── health/
```

Each report run:

- Writes manifest (git commit, env fingerprint)
- Records SHA256 of artifacts
- Updates run registry

Research outputs are reproducible and versioned.

---

## 10. Governance & Reproducibility

- `crypto_analyzer.doctor`
- Run manifests
- Health summary
- Deterministic universe selection
- Persistence + churn logging
- Optional strict integrity mode

Designed for institutional research audit trails.

---

## 11. Troubleshooting

If you see **ModuleNotFoundError**, you are outside the venv.

Use:

```powershell
.\scripts\run.ps1 <command>
```

or

```powershell
.\.venv\Scripts\python.exe <script>.py
```

---

## 12. Limitations

- Dependent on DEX API data quality
- Short histories produce unstable Sharpe
- Slippage model is a proxy
- No execution layer

---

## 13. Research-Only Disclaimer

This repository is strictly for research.

It does **not**:

- Execute trades
- Connect to brokers
- Manage positions
- Sign transactions

All analytics and backtests are theoretical estimates.

---

## 14. Project Layout

| Path | Purpose |
|------|--------|
| `crypto_analyzer/` | Core package |
| `dex_poll_to_sqlite.py` | Poller |
| `materialize_bars.py` | Bar builder |
| `dex_scan.py` | Scanner |
| `backtest.py` | Backtests |
| `research_report_v2.py` | Advanced research |
| `app.py` | Streamlit UI |
| `scripts/run.ps1` | Helper runner |
| `tests/` | Pytest suite |

---

## 15. Documentation

- **docs/INSTITUTIONAL.md**
- **CONTRIBUTING.md**
- **DEPLOY.md**
- **WINDOWS_24_7.md**

---

## 16. License

See repository license file.
