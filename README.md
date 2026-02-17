# Crypto-Analyzer

Systematic digital-asset research platform for factor modeling, regime detection, and robust validation. **Research-only:** no execution, no trading keys, no broker/exchange connectivity, no order routing.

---

## 1. System Overview

Crypto-Analyzer is a cross-asset quantitative research engine built on DEX snapshot ingestion, deterministic bar materialization, factor modeling (BTC/ETH beta + residuals), cross-sectional signal validation, portfolio research with cost modeling, and governance/reproducibility controls. It operates under institutional research constraints: auditability, stability, and statistical discipline.

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

- **Single source of truth:** `dex_data.sqlite`. All analytics consume the same normalized bars and factor series.
- **Configuration:** `config.yaml` + `config.py` (DB path, universe, filters).
- See **ARCHITECTURE.md** for module-level diagram and responsibility table.

---

## 3. Data Flow

**Ingestion** — `dex_poll_to_sqlite.py` polls DEX + spot data into SQLite.

**Materialization** — `materialize_bars.py` builds deterministic OHLC bars (5min, 15min, 1h, 1D).

**Features** — `crypto_analyzer.features` (returns, vol, drawdown, regime). Downstream: `dex_analyze.py`, `dex_scan.py`, `backtest.py`, `backtest_walkforward.py`, `research_report.py`, `research_report_v2.py`, `app.py` (Streamlit). All use the same DB and config.

---

## 4. Core Research Modules

Factor modeling (BTC beta, residuals, beta compression). Regime classification (vol, dispersion, beta state). Signals (momentum, residual momentum, dispersion extremes) — research only, no execution. Cross-sectional research (Spearman IC, IC decay, turnover, regime-conditioned IC). Portfolio research (vol targeting, risk parity, beta neutrality, cost modeling). Overfitting controls (walk-forward, block bootstrap, deflated Sharpe, PBO proxy, experiment logging).

---

## 5. Validation Framework

Strict no-lookahead; walk-forward train/test separation; frequency-consistent annualization. Optional **strict integrity** (`--strict-integrity`, `--strict-integrity-pct`) exits with code 4 if bad row rate exceeds threshold. Default is warn-only; strict mode is opt-in for pipelines.

---

## 6. Quickstart

From repo root (use helper script so venv is used):

```powershell
.\scripts\run.ps1 doctor
.\scripts\run.ps1 universe-poll --universe --universe-chain solana --interval 60 --universe-debug 5
.\scripts\run.ps1 materialize --freq 1h
.\scripts\run.ps1 reportv2 --freq 1h --out-dir reports
.\scripts\run.ps1 streamlit
```

**Commands:** `poll`, `universe-poll`, `materialize`, `report`, `reportv2`, `streamlit`, `doctor`, `test`. Confirm universe logs show `Dex pairs: X (universe_mode=True)` and `Universe refreshed: N pairs`. If `universe_mode=False`, you did not pass `--universe`.

---

## 7. Universe Mode (Multi-Asset)

Universe discovery uses Dexscreener public search: multi-query, merge by pair address, deterministic ranking (liquidity, volume, label, address). Quality filters: liquidity/24h volume, reject same-symbol and stable/stable, quote allowlist (default USDC/USDT). **Stability:** `max_churn_pct` (0.20), `min_persistence_refreshes` (2). **Audit tables:** `universe_allowlist`, `universe_churn_log`, `universe_persistence`. Verify with `python check_universe.py`. Operator sanity: 3+ allowlist refreshes, stable N, minimal churn (0–1 add/remove typical).

---

## 8. Streamlit Interface

`.\scripts\run.ps1 streamlit` — Overview, Scanner, Backtest, Walk-Forward, Market Structure, Signals, Research, Institutional Research, Runtime / Health, Governance. UI degrades when asset count &lt; 3.

---

## 9. Reports & Artifacts

Reports write to `reports/` (csv/, charts/, manifests/, health/). Each run writes a manifest (commit, env fingerprint, artifact SHAs). Strict integrity: `.\scripts\run.ps1 reportv2 --strict-integrity --strict-integrity-pct 1`.

---

## 10. Governance & Reproducibility

Doctor, run manifests, health summary, deterministic universe selection, persistence + churn logging, optional strict integrity. Designed for institutional audit trails.

---

## 11. Troubleshooting

**ModuleNotFoundError** — Run outside venv. Use `.\scripts\run.ps1 <command>` or `.\.venv\Scripts\python.exe <script>.py`.

---

## 12. Limitations

DEX API data quality; short histories → unstable Sharpe; slippage model is a proxy; no execution layer.

---

## 13. Research-Only Disclaimer

This repository is strictly for research. It does not execute trades, connect to brokers, manage positions, or sign transactions. All analytics and backtests are theoretical estimates.

---

## 14. Project Layout

| Path | Purpose |
|------|--------|
| **Entrypoints** | |
| `dex_poll_to_sqlite.py` | Poller (single-pair or universe) |
| `materialize_bars.py` | Bar builder |
| `dex_analyze.py` | Leaderboard |
| `dex_scan.py` | Scanner |
| `backtest.py`, `backtest_walkforward.py` | Backtests |
| `report_daily.py`, `research_report.py`, `research_report_v2.py` | Reports |
| `app.py` | Streamlit UI |
| **Helpers** | |
| `check_universe.py` | Universe allowlist/churn verification |
| `sanity_check.py`, `sanity_check_m5.py` | System health checks |
| `scripts/run.ps1` | Venv-backed runner (primary CLI) |
| `config.yaml` | DB, universe, filters |
| **Package** | |
| `crypto_analyzer/` | Core package |
| `tests/` | Pytest suite |

Legacy/optional scripts in root (see docs): `dashboard.py`, `check_db.py`, `clear_db_data.py`, `analyze_from_sqlite.py`, `dex_discover.py`. Prefer `app.py`, `doctor`, and `.\scripts\run.ps1` for primary workflows.

---

## 15. Documentation

- **docs/INSTITUTIONAL.md** — Institutional research principles
- **CONTRIBUTING.md** — Code style, testing, commit messages, research-only boundary
- **DEPLOY.md** — Deploying the dashboard
- **WINDOWS_24_7.md** — Running the poller 24/7
- **HANDOFF_AUTOPOLLING.md** — Poller and NSSM (Windows)
- **docs/CLEANUP_SUMMARY.md** — Past cleanup notes (status: historical)
- **docs/FOUNDERS_AUDIT.md** — First-impression checklist, entrypoints, minimal demo, GitHub About/topics

---

## 16. License

MIT License. See LICENSE.
