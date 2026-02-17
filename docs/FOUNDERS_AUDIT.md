# Founders / Public Launch Audit

One-page view for recruiter/investor first impression and minimal demo.

---

## First impression checklist (30 seconds)

- [ ] **README** — One-line tagline + “Research-only” in opening; numbered sections; high-level diagram; Quickstart uses `.\scripts\run.ps1`
- [ ] **No execution claims** — No order routing, broker keys, wallets, or live trading
- [ ] **Architecture** — Single source of truth (SQLite); config separate; ARCHITECTURE.md linked
- [ ] **Project layout** — Entrypoints and helpers listed; legacy scripts called out
- [ ] **Docs index** — INSTITUTIONAL, CONTRIBUTING, DEPLOY, WINDOWS_24_7, HANDOFF_AUTOPOLLING, CLEANUP_SUMMARY (historical)

---

## Blessed entrypoints

| Command / script | Purpose |
|------------------|--------|
| `.\scripts\run.ps1 doctor` | Preflight (env, DB, pipeline smoke) |
| `.\scripts\run.ps1 universe-poll --universe ...` | Multi-asset poller |
| `.\scripts\run.ps1 materialize` | Build bars from snapshots |
| `.\scripts\run.ps1 reportv2 --freq 1h --out-dir reports` | Research report |
| `.\scripts\run.ps1 streamlit` | Streamlit UI |
| `.\scripts\run.ps1 test` | Pytest suite |
| `python check_universe.py` | Universe allowlist/churn verification |

Root entrypoints (same logic via venv): `dex_poll_to_sqlite.py`, `materialize_bars.py`, `dex_analyze.py`, `dex_scan.py`, `backtest.py`, `backtest_walkforward.py`, `report_daily.py`, `research_report.py`, `research_report_v2.py`, `app.py`.

---

## Intentionally research-only

- No execution, no order routing, no broker/exchange connectivity, no trading API keys, no wallet signing, no position management.
- All backtests, reports, and dashboard outputs are theoretical estimates for study and validation.
- Any live or paper trading use is outside this repository.

---

## Minimal demo (3 commands)

From repo root with venv set up:

```powershell
.\scripts\run.ps1 doctor
.\scripts\run.ps1 universe-poll --universe --universe-chain solana --interval 60 --universe-debug 5
.\scripts\run.ps1 streamlit
```

Then open http://localhost:8501. (With no data, Overview may show empty; run materialize + reportv2 when DB has bars for full pipeline.)

---

## Remaining rough edges (honest)

- Root has legacy/optional scripts (`dashboard.py`, `check_db.py`, `clear_db_data.py`, `analyze_from_sqlite.py`, `dex_discover.py`) alongside blessed entrypoints; documented as legacy in README; no behavior change.
- Some docs (e.g. CLEANUP_SUMMARY) are historical; marked in docs index.
- GitHub “About” and topics must be set manually on the repo (see below).

---

## Recommended GitHub “About” and topics

**Short description (About):**

> Research-only DEX & factor analytics: snapshots → bars → backtests, reports, Streamlit. No execution.

**Extended (if supported):**

> Cross-asset quantitative research platform: DEX snapshot ingestion, deterministic bar materialization, factor modeling (BTC/ETH beta + residuals), cross-sectional validation, portfolio research, governance/reproducibility. Research-only; no execution, no trading keys.

**Topics (tags):**

`research` `crypto` `backtesting` `streamlit` `factor-models` `dex` `quantitative-finance` `python`
