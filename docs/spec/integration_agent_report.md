# Post-merge integration agent report

## 1) Changes applied (per checklist item)

### Unify busy_timeout config usage + PRAGMA consistency

- **Files changed:** `crypto_analyzer/ingest/__init__.py`
- **What was changed:**
  - `_apply_ingestion_pragmas` now calls `db_busy_timeout_ms()` from config instead of hardcoded `5000`.
  - Added `PRAGMA foreign_keys=ON` so ingestion matches read_api pragmas.
- **Why:** Avoids config/read path divergence and ensures foreign_keys are on for both read and write connections (conflict/risk: Agent B allowlists and DB open behavior).

### ProviderHealthStore commit semantics

- **Files changed:** `crypto_analyzer/ingest/__init__.py` (no code change; already correct), `tests/test_db_provenance.py`
- **What was changed:**
  - Confirmed all in-transaction call sites pass `commit=False` (ingest `run_one_cycle` only).
  - Added `test_upsert_commit_false_does_not_commit_until_caller_commits`: second connection sees 0 rows until first connection commits.
- **Why:** Ensures no partial commit if something fails after health upsert (risk: rollback semantics).

### Validate allowlists match schema

- **Files changed:** None (audit only).
- **What was changed:**
  - Confirmed `ALLOWED_SNAPSHOT_TABLES = {"sol_monitor_snapshots"}`, `ALLOWED_PRICE_COLUMNS = {"dex_price_usd", "price_usd"}`; migrations and writer use `sol_monitor_snapshots` and `dex_price_usd`.
- **Why:** Agent B allowlists could conflict with actual schema; audit shows they match.

### Harden UI against raised DB exceptions

- **Files changed:** `cli/app.py`, `cli/dashboard.py` (done in prior integration pass).
- **What was changed:**
  - Streamlit pages wrap `load_*` / `read_api.*` in try/except and show “No data yet—run poll” (or materialize/allowlist) instead of stack traces.
  - Dashboard DB load block wrapped in try/except with safe defaults and “No data yet—run poll.”
- **Why:** Agent B’s raise-on-error policy would surface in UI; friendly messages avoid user-facing tracebacks.

### Remove library → CLI import (doctor)

- **Files changed:** `crypto_analyzer/doctor.py`
- **What was changed:**
  - `_warn_universe_zero_if_enabled` no longer imports `poll` (no `sys.path` + `from poll import ...`). When universe is enabled it prints an [INFO] line with the universe-poll command; no one-shot fetch.
- **Why:** Library must not depend on CLI; doctor is in `crypto_analyzer` and must not pull in `cli/poll`.

### DEX table empty / missing table (prior pass)

- **Files changed:** `crypto_analyzer/data.py`, `tests/test_data_loaders.py`
- **What was changed:**
  - `load_snapshots` and `load_bars` catch “no such table” (including pandas-wrapped), warn, and return empty DataFrame instead of raising.
  - Test renamed to `test_load_bars_no_such_table_returns_empty`.
- **Why:** Downstream and UI handle “DEX table empty” or missing bars table without crashes.

---

## 2) Repo-wide grep audit

### upsert( / upsert_all( call sites and commit=False

| Location | Call | commit=False? |
|----------|------|----------------|
| `crypto_analyzer/db/health.py` | `def upsert(..., commit=True)` | N/A (definition) |
| `crypto_analyzer/db/health.py` | `def upsert_all(..., commit=True)`; internally `self.upsert(h, commit=False)` | N/A (definition) |
| `crypto_analyzer/ingest/__init__.py` | `ctx.health_store.upsert_all(..., commit=False)` (×2) | **Yes** |
| `tests/test_db_provenance.py` | `store.upsert(health)` etc. | No (tests commit explicitly or use default) |
| `tests/test_provider_integration.py` | `health_store.upsert_all(spot_chain.get_health())` (×2) | No (standalone test, no outer transaction) |

**Summary:** Only in-transaction call site is ingest; it passes `commit=False`. Tests that need to commit use default or explicit commit; no in-transaction test incorrectly commits.

### sys.path.insert

- **Matches:** Many files.
- **In `crypto_analyzer/` (library):** **None.** (Doctor previously used it to import poll; that was removed.)
- **In `cli/`:** Yes — `app.py`, `research_report_v2.py`, `poll.py`, `report_daily.py`, `api.py`, `demo.py`, `scan.py`, `backtest*.py`, `materialize.py`, `analyze.py`, `promotion.py`, `null_suite.py`, etc. All are CLI or tools that need repo root on path.
- **In `tests/`:** Yes — numerous test files insert repo root (and sometimes `cli`) so they can import app or cli modules.
- **Conclusion:** No `sys.path.insert` remains in the library (`crypto_analyzer/`). All uses are in CLI or tests.

### SQL table names in data.py / read_api.py vs allowlists

**data.py:**

| Source | Table(s) | Allowlist / validation |
|--------|----------|------------------------|
| `load_snapshots` | `table` from `db_table()` or `table_override` | `ALLOWED_SNAPSHOT_TABLES` (sol_monitor_snapshots) |
| `load_bars` | `bars_{freq}` | `allowed_bars_tables()` from config bars_freqs |
| `load_spot_series` | `spot_price_snapshots` (hardcoded) | Not in snapshot allowlist (different API) |
| `load_snapshots_as_bars` | same as load_snapshots | same |
| `load_factor_run` | `factor_betas`, `residual_returns` | No allowlist (phase 2+ tables) |

**read_api.py:**

| Function | Table(s) |
|----------|----------|
| `load_spot_snapshots_recent` | spot_price_snapshots |
| `load_latest_universe_allowlist` | universe_allowlist |
| `load_universe_allowlist_stats` | universe_allowlist |
| `load_universe_churn_verification` | universe_allowlist, universe_churn_log |

**Config allowlists:** `ALLOWED_SNAPSHOT_TABLES = frozenset({"sol_monitor_snapshots"})`, `ALLOWED_PRICE_COLUMNS = frozenset({"dex_price_usd", "price_usd"})`. `allowed_bars_tables()` = bars_5min, bars_15min, bars_1h, bars_1D from config.

**Conclusion:** Snapshot/bars tables used in data loaders are validated against allowlists. read_api uses spot_price_snapshots, universe_allowlist, universe_churn_log (no allowlist in config; these are fixed read-only entry points). Schema and allowlists align.

---

## 3) New failure modes check (Agent B raise-on-error)

Every UI/CLI entrypoint that calls read functions:

| Entrypoint | Read calls | Handled? | How |
|------------|------------|----------|-----|
| **cli/app.py** (Streamlit) | load_leaderboard, load_bars, load_latest_universe_allowlist, load_signals, load_manifests, load_experiment*, read_api.load_spot_snapshots_recent, load_universe_allowlist_stats, load_universe_churn_verification, get_research_assets, load_spot_price_resampled, append_spot_returns_to_returns_df | **Yes** | try/except; empty DataFrame or friendly “No data yet—run poll” / “run materialize” / “run reportv2” |
| **cli/dashboard.py** | load_tables, load_sol_monitor, load_spot_prices (raw SQL on conn) | **Yes** | Whole DB load in try/except; on exception show “No data yet—run poll” and st.stop() |
| **cli/report_daily.py** | load_bars, load_snapshots, load_spot_price_resampled, load_signals | **No** | CLI script; allowed to crash with traceback (batch job; documented by “run poll / materialize” in errors) |
| **cli/scan.py** | load_bars, load_snapshots (via _load_bars_or_snapshots) | **Partial** | load_bars now returns empty on missing table; snapshots return empty; scan returns empty result, no crash |
| **cli/backtest.py** | load_bars | **No** | CLI; allowed to crash (user must run materialize first) |
| **cli/backtest_walkforward.py** | load_bars | **No** | CLI; allowed to crash |
| **cli/research_report_v2.py** | get_research_assets, load_factor_run, load_cached_null_max | **No** | CLI; allowed to crash with clear errors (e.g. “Need >= 3 assets”) |
| **cli/research_report.py** | get_research_assets | **No** | CLI |
| **cli/materialize.py** | load_bars, load_snapshots | **No** | CLI |
| **cli/analyze.py** | load_snapshots (local), load_spot_price_resampled | **No** | CLI |
| **crypto_analyzer/doctor.py** | config, load_bars, get_research_assets, count_non_positive_prices, dataset fingerprint | **Partial** | load_bars returns empty on missing table; get_research_assets can still raise; doctor prints “[FAIL] pipeline smoke” and exits 4 |

**Summary:** All **Streamlit** entrypoints (app.py, dashboard.py) catch and show friendly messages. **CLI** entrypoints are intentionally allowed to crash with tracebacks or explicit error messages; no doc change required for that contract. Doctor is hardened by data layer returning empty for missing tables; pipeline smoke can still fail with a clear message.

---

## 4) End-to-end sanity run

No single “fresh DB → one cycle → read → walkforward → pipeline” script exists. Coverage is via existing tests:

| Step | Covered by |
|------|------------|
| Create empty DB | test_data_loaders (temp DB, no bars table), test_read_api (empty DB), test_db_provenance (in-memory), test_ingest_cycle (temp DB) |
| One ingestion cycle (fakes) | test_ingest_cycle (run_one_cycle with fakes), test_ingest_context |
| Read path (read_api / data loader) | test_read_api (empty + with rows), test_data_loaders (load_snapshots, load_bars, load_spot_series; missing table → empty) |
| Walk-forward import | test suite imports and runs backtest_walkforward-related code; test_research_pipeline_smoke runs pipeline |
| Research pipeline demo bundle | tests/test_research_pipeline_smoke.py (builds bundle, hashes.json, manifest) |

**Run executed:**  
`pytest tests/test_db_provenance.py tests/test_ingest_cycle.py tests/test_data_loaders.py tests/test_read_api.py tests/test_research_pipeline_smoke.py -q --tb=line`

**Result:** 41 passed, 1 warning (expected UserWarning for missing bars_1h in test_load_bars_no_such_table_returns_empty).

---

## 5) Final proof: command outputs

### Pytest summary (subset above)

```
41 passed, 1 warning in 55.25s
```

(Warning: `UserWarning: load_bars: table 'bars_1h' does not exist ...` in test_load_bars_no_such_table_returns_empty — expected.)

Full suite: run `.\scripts\run.ps1 test` or `python -m pytest tests/ -q`; may take several minutes.

### Ruff check summary

```
Found 3 errors.
[*] 3 fixable with the `--fix` option.
```

All 3 are **import order** (I001) in test files:

- tests/test_reportv2_reality_check_optional.py  
- tests/test_reportv2_regime_conditioned_artifacts.py  
- tests/test_reportv2_regimes_optional.py  

Fix: `ruff check . --fix` then `ruff format .` if desired. No errors in `crypto_analyzer/` or `cli/` from integration changes.

### Before/after behavioral changes

| Scenario | Before | After |
|----------|--------|--------|
| Empty DB or missing bars table | load_bars could raise (e.g. FileNotFoundError or OperationalError) | load_bars returns empty DataFrame and warns; UI shows “No data yet—run poll.” |
| Missing snapshot table (DEX skipped) | load_snapshots raised OperationalError | load_snapshots returns empty DataFrame and warns; UI shows “No data yet—run poll.” |
| Streamlit with bad DB path or missing table | Unhandled exception, stack trace | try/except in app/dashboard; “No data yet—run poll.” or “run materialize” |
| Doctor with universe enabled | Imported cli/poll (library → CLI) | No poll import; prints [INFO] with universe-poll command |
| Ingestion pragmas | busy_timeout=5000 hardcoded; no foreign_keys | busy_timeout from config (`db_busy_timeout_ms()`); PRAGMA foreign_keys=ON |
| ProviderHealthStore in transaction | Same behavior (already commit=False) | Same; test added proving commit=False does not commit until caller commits |

---

**Commands to run**

```powershell
.\scripts\run.ps1 test
# or
python -m pytest tests/ -q

python -m ruff check . --fix
python -m ruff format .
```

**What to look for:** All tests pass; ruff clean (or only benign I001 fixes in tests); UI and doctor behave as in the table above.

---

## Post-report fixes (merge gate)

- **Ruff I001:** Ran `ruff check . --fix` and `ruff format .`; **ruff check .** is clean (All checks passed).
- **Windows test flake:** `test_reportv2_factor_run_id_valid_uses_materialized` could raise `PermissionError` when unlinking temp SQLite (file still in use). Cleanup in that file now wraps `Path(...).unlink()` in `try/except OSError`.
- **Config:** Added a short comment in `config.py` above allowlists: how to extend tables/columns safely so load_snapshots/load_bars stay in sync with migrations.

**Final gate (run once):**

- `python -m pytest tests/ -q` → **399 passed, 3 skipped, 1 warning** (expected UserWarning for missing bars table).
- `python -m ruff check .` → **All checks passed.**
- `python -m crypto_analyzer.doctor` → runs from repo root (no CLI import).
- Streamlit with empty DB → shows “No data yet—run poll” (no traceback).

---

## Optional polish backlog (future UX pass)

Not required for merge; capture for later if desired:

1. **CLI “no such table” helper**  
   Add a small helper that catches `sqlite3.OperationalError` (e.g. “no such table”) in CLI entrypoints (backtest, walkforward, report_daily, etc.) and prints a one-liner: *“Run poll then materialize first.”* plus the exact command from the README (e.g. `.\scripts\run.ps1 poll`, then `materialize --freq 1h`).

2. **End-to-end smoke script**  
   Add e.g. `scripts/smoke.py` that: creates a temp DB → runs one fake ingest cycle → runs read path (read_api / data loaders) → runs pipeline demo bundle. Single script to prove “fresh DB → ingest → read → pipeline” without relying only on scattered tests.
