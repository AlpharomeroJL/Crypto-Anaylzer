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

Output directory: `reports/` (configurable via `--out-dir`). Under `reports/`: `csv/`, `charts/`, `manifests/`, `health/`. Research reports write run manifests (git commit, env fingerprint, data window, outputs with SHA256) to `reports/manifests/` when `--save-manifest` (default). V2 also writes a research health summary to `reports/health/health_summary.json`. **Strict integrity:** Use `--strict-integrity` (and optional `--strict-integrity-pct 5`) with `research_report.py` or `research_report_v2.py` to exit with code 4 if any checked table/column has bad row rate above the threshold (default 5%); useful for institutional pipelines. Default behavior stays warn-only so normal runs are never broken. Example (fail fast when you want it):

```powershell
.\scripts\run.ps1 reportv2 --strict-integrity --strict-integrity-pct 1
```

---

## Streamlit Interface

```powershell
streamlit run app.py
```

Open http://localhost:8501. Pages: Overview (universe size, top pairs by liquidity, latest universe allowlist), Pair detail, Scanner, Backtest, Walk-Forward, Market Structure, Signals, **Research**, **Institutional Research**, **Runtime / Health** (universe last refresh, recommended commands, latest manifest/health), **Governance** (manifests, health summary, download JSON). With fewer than 3 assets, Research shows a message; Institutional Research degrades gracefully.

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

**If you see `ModuleNotFoundError` (e.g. for `requests`):** You're likely running outside the venv. Either activate it (`.\.venv\Scripts\Activate`) or run commands with the venv Python explicitly: `.\.venv\Scripts\python.exe -m ...` or use `.\scripts\run.ps1 <command>`.

---

## System Doctor

One-command preflight to verify environment, dependencies, DB, integrity, and a minimal pipeline smoke:

```powershell
.\.venv\Scripts\python.exe -m crypto_analyzer.doctor
```

Exit codes: 0 = OK, 2 = env/deps, 3 = DB/schema, 4 = pipeline smoke. If not in venv, the doctor prints the exact command to run (e.g. activate then `python -m crypto_analyzer.doctor`).

---

## Configuration

- **config.yaml:** DB path, table, price column, timezone, default freq/window, min liquidity, min vol24, min bars, bars_freqs.
- **Environment:** `CRYPTO_DB_PATH`, `CRYPTO_TABLE`, `CRYPTO_PRICE_COLUMN`.

Default DB: `dex_data.sqlite`, table: `sol_monitor_snapshots`, price: `dex_price_usd`.

---

## Run the Stack

Prefer running with the venv Python so dependencies are guaranteed. **If you see `ModuleNotFoundError` (e.g. `requests`), you're running outside the venv** — use `.\.venv\Scripts\python.exe` or the helper script below. From repo root:

```powershell
.\.venv\Scripts\python.exe dex_poll_to_sqlite.py --interval 60
.\.venv\Scripts\python.exe -m streamlit run app.py
```

**Helper script** (uses venv automatically): `.\scripts\run.ps1 <command> [args]`. Commands: `poll`, `universe-poll`, `materialize`, `report`, `reportv2`, `streamlit`, `doctor`, `test`. Example: `.\scripts\run.ps1 reportv2 --freq 1h --out-dir reports`.

**1. Poller (populate data)**

```powershell
.\.venv\Scripts\python.exe dex_poll_to_sqlite.py --interval 60
```

Creates DB and tables. Pairs from `config.yaml` `pairs` or `--pair CHAIN_ID:PAIR_ADDRESS` (repeatable).

**Universe mode (multi-asset):** To poll top DEX pairs by chain from Dexscreener’s public API (no API keys), use either `--universe` or `--universe top`:

```powershell
.\.venv\Scripts\python.exe dex_poll_to_sqlite.py --universe top --universe-chain solana --universe-refresh-minutes 60 --interval 60
# or
.\.venv\Scripts\python.exe dex_poll_to_sqlite.py --universe --universe-chain solana --interval 60
```

**Tradeable universe (institutional defaults):** Discovery uses multiple search queries (default per chain: Solana USDC/USDT/SOL) so you get SOL/USDC pairs, not only SOL/SOL. Quality gates reject garbage pairs, require liquidity and volume, and restrict to quote allowlist (default USDC/USDT). Stable/stable pairs are rejected by default. Known-good Solana example:

```powershell
.\scripts\run.ps1 universe-poll --universe --universe-chain solana --universe-query USDC --universe-query USDT --interval 60 --universe-debug 20
```

With min liquidity/volume:

```powershell
.\scripts\run.ps1 universe-poll --universe --universe-chain solana --universe-min-liquidity 50000 --universe-min-vol-h24 50000 --universe-debug 20 --interval 60
```

**Start it explicitly in universe mode** (from repo root). You must pass `--universe` or you will run in single-pair mode:

```powershell
.\scripts\run.ps1 universe-poll --universe --universe-chain solana --interval 60 --universe-debug 5
```

Confirm in the log: **`Dex pairs: X (universe_mode=True)`** and **`Universe refreshed: N pairs`**. If you see `universe_mode=False`, you did not pass `--universe`.

- **`--universe-query Q`** (repeatable) overrides config search queries; e.g. `--universe-query USDC --universe-query USDT` for broader discovery.
- **`universe.queries`** in `config.yaml` (default Solana: `["USDC","USDT","SOL"]`) sets search terms; results are merged and de-duplicated by pair address.
- Default quote allowlist is **USDC/USDT**; SOL/SOL and stable/stable pools are rejected by default.
- To override allowlist (not recommended): `--universe-quote-allowlist "USDC,USDT,SOL"`.
- If the universe is empty after filters, the poller first tries **relaxed** thresholds (0.25× min liquidity/volume), then optional **`universe.bootstrap_pairs`** in config (chain-matched), then configured pairs. Each fallback path is logged.

Configure in `config.yaml` under `universe`: `enabled`, `chain_id`, `page_size`, `refresh_minutes`, `min_liquidity_usd`, `min_vol_h24`, `queries`, `quote_allowlist`, `reject_same_symbol`, `reject_stable_stable`, **`max_churn_pct`** (default `0.20`), **`min_persistence_refreshes`** (default `2`; require pair to fail selection K refreshes before removal; `0` = disable), and optional **`bootstrap_pairs`**. CLI overrides: **`--universe-max-churn-pct`** (float; `1.0` = no churn limit), **`--universe-min-persistence-refreshes`** (int; K).

**Universe stability (churn control):** To avoid thrashing the allowlist on each refresh, the poller limits how many pairs can be replaced per cycle. `universe.max_churn_pct` (default `0.20`) caps replacements at `ceil(previous_size × max_churn_pct)` while keeping all overlapping pairs. Set to `1.0` to allow full churn. Log line: *Universe churn: kept=X replaced=Y max_allowed=Z*.

**Minimum persistence:** Once a pair is on the allowlist, it must fail selection for **K** consecutive refreshes (default `min_persistence_refreshes: 2`) before it can be removed. This avoids one-off API glitches dropping pairs. Set to `0` to disable.

**Churn audit:** Removals and additions are logged to `universe_churn_log` (action is `add` or `remove`, plus reason, liquidity_usd, vol_h24). Allowlist rows can include `reason_added` (overlap, sticky, churn_replace, bootstrap_pairs, etc.). *Transition:* Old rows may still have `added`/`removed`; mixed history is expected. If any query filters by action, use `WHERE action IN ('add','remove','added','removed')` until you migrate. Optional one-off migration: `UPDATE universe_churn_log SET action='add' WHERE action='added';` and same for `'remove'`/`'removed'`.

**Universe verification (once universe selects >0 pairs):** Run the poller for 10–15 minutes, then materialize 1h bars. Confirm multiple pairs have bars: `SELECT COUNT(DISTINCT chain_id || ':' || pair_address) FROM bars_1h;` should be > 1. In the Streamlit app: **Overview** should show "Universe size" > 1, **Top pairs by liquidity**, and **Latest universe allowlist (audit)** (top 20 from `universe_allowlist`); **Scanner** should show more than one row when you run a scan.

**Allowlist audit table:** Each universe refresh writes the active allowlist to `universe_allowlist` (columns: `ts_utc`, `chain_id`, `pair_address`, `label`, `liquidity_usd`, `vol_h24`, `source`, `query_summary`). **Operator verification (copy-paste into SQLite):**

```sql
-- Latest allowlist size + sources (last 5 refreshes)
SELECT ts_utc, COUNT(*) AS n, MIN(source) AS sources_hint
FROM universe_allowlist
GROUP BY ts_utc
ORDER BY ts_utc DESC
LIMIT 5;

-- Churn since last refresh
SELECT action, reason, COUNT(*) AS n
FROM universe_churn_log
WHERE ts_utc = (SELECT MAX(ts_utc) FROM universe_churn_log)
GROUP BY action, reason
ORDER BY n DESC;
```

If those look right (n per ts_utc, sources_hint, and churn action/reason counts), universe mode is auditable and closed.

**Final check (production-stable, research-grade):** (1) Run universe-poll long enough to get at least 3 distinct `ts_utc` values in `universe_allowlist`. (2) Run `python check_universe.py`. **Allowlist:** you want multiple rows like `(ts1, N, universe)`, `(ts2, N, universe)`, `(ts3, N, universe)` with stable N. **Churn:** at the latest churn timestamp, ideally 0–1 add and 0–1 remove (e.g. `('add', 'churn_replace', 0–1)`, `('remove', 'churn_replace', 0–1)`) or no churn. If you see 2–4 adds and 2–4 removes every refresh, that’s thrash → tighten `max_churn_pct`, raise thresholds, or increase `min_persistence_refreshes`. If allowlist and churn look sane after 3+ refreshes, the universe system is production-stable. (Old churn rows may still show `added`/`removed`; mixed history is fine; the verification query groups by action and works without changes.)

**Deep check (optional):** To confirm whether the poller rewrites allowlist rows every refresh vs only when the set changes, run in interactive Python:

```python
import sqlite3
conn = sqlite3.connect("dex_data.sqlite")
print(conn.execute("""
SELECT ts_utc, action, reason, COUNT(*)
FROM universe_churn_log
GROUP BY ts_utc, action, reason
ORDER BY ts_utc DESC
LIMIT 20
""").fetchall())
conn.close()
```

If you see `add 4` (or similar) every refresh, churn logging may be recording “add” even when the pair set didn’t change (easy to tighten later). From an operator standpoint, allowlist stability is already correct. Net: you’re in the **production-stable, research-grade** zone for universe polling.

**Operational guardrail:** On each universe refresh, the poller logs the top 5 selected pairs (label + full address) so operators can confirm which pairs are active. It also logs a **persistence** line when `min_persistence_refreshes` >= 1: `[persistence] overlap=X kept_sticky=Y failures_inc=Z removed_K=W max_streak_top3=[...]` so you can confirm K is working without digging into SQL.

**Operator sanity (2–3 commands):** To prove universe mode is stable, auditable, and reproducible (even after restarts): (1) Run `.\scripts\run.ps1 doctor`, then `.\scripts\run.ps1 universe-poll --universe --universe-chain solana --interval 60 --universe-debug 20` and wait for 2 refreshes. (2) Check logs for `Universe churn:` and `[persistence]` lines. (3) Run the two verification SQL queries above (or open **Runtime / Health** in Streamlit and check the audit tables). If allowlist size + sources and churn action/reason counts look right, you’re closed.

**2. Materialize bars**

```powershell
.\.venv\Scripts\python.exe materialize_bars.py
# Or: .\.venv\Scripts\python.exe materialize_bars.py --freq 1h
```

**3. Analyze**

```powershell
.\.venv\Scripts\python.exe dex_analyze.py --freq 1h --window 24
.\.venv\Scripts\python.exe dex_analyze.py --freq 1h --top 10
```

**4. Scanner**

```powershell
.\.venv\Scripts\python.exe dex_scan.py --mode momentum --freq 1h --top 5
.\.venv\Scripts\python.exe dex_scan.py --mode volatility_breakout --freq 1h --z 2.0
```

**5. Backtest**

```powershell
.\.venv\Scripts\python.exe backtest.py --strategy trend --freq 1h
.\.venv\Scripts\python.exe backtest_walkforward.py --strategy trend --freq 1h --train-days 30 --test-days 7 --step-days 7
```

**6. Reports**

```powershell
.\.venv\Scripts\python.exe report_daily.py
.\.venv\Scripts\python.exe research_report.py --freq 1h --save-charts
.\.venv\Scripts\python.exe research_report_v2.py --freq 1h --out-dir reports
```

**Acceptance commands (verify stack):** These should run without error when venv is active and (for report/poller) data exists:

- `.\.venv\Scripts\python.exe -m crypto_analyzer.doctor`
- `.\.venv\Scripts\python.exe research_report_v2.py --freq 1h --out-dir reports`
- `.\.venv\Scripts\python.exe dex_poll_to_sqlite.py --universe`
- `.\.venv\Scripts\python.exe -m streamlit run app.py`

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
