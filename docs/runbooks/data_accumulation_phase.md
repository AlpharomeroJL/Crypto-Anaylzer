# Operator runbook: real-data accumulation (poll → materialize → reportv2)

Use this during the **data accumulation** phase before the next golden `reportv2` proof run. Goal: wider calendar span and stronger panel support without changing promotion thresholds or research methodology.

## Canonical commands (leave running)

From repo root, with venv active (or `.\scripts\run.ps1`):

**Universe mode (recommended for breadth)** — requires `universe.enabled: true` in `config.yaml`:

```powershell
.\scripts\run.ps1 universe-poll --log-file logs\poll_universe.log
```

Equivalent:

```powershell
python -m crypto_analyzer poll --universe top --log-file logs\poll_universe.log
```

**Static / config pairs only** (no universe refresh):

```powershell
.\scripts\run.ps1 poll --log-file logs\poll.log
```

**Explicit database** (matches golden docs / multi-machine setups):

```powershell
python -m crypto_analyzer poll --universe top --db .\dex_data.sqlite --log-file logs\poll_universe.log
```

Poll now uses **`config.yaml` `db.path`** and **`CRYPTO_DB_PATH`** when `--db` is omitted (aligned with `materialize` / `reportv2`).

**Relative** `db.path` / `CRYPTO_DB_PATH` values are resolved against the **repo root** (parent of `crypto_analyzer/`), not the process current directory—same target as `python -m crypto_analyzer doctor` shows.

## Where data lands

| Artifact | Location |
|----------|----------|
| SQLite (default) | Path from `db.path` in `config.yaml`, or `CRYPTO_DB_PATH`, or `--db` (relative config/env paths → repo root) |
| Spot snapshots | Table `spot_price_snapshots` |
| DEX snapshots | Table `sol_monitor_snapshots` (default; see `db.table` in config) |
| Optional operator log | Path passed to `--log-file` |

After enough snapshots exist, **materialize** bars before research:

```powershell
.\scripts\run.ps1 materialize --freq 1h
```

Use the **same** DB path for `materialize` and `reportv2` (config, env, or `--db` on each command).

**Report outputs:** `reportv2` defaults to **`reports/reportv2/`** (markdown at that root, with `csv/`, `manifests/`, `health/`, etc. underneath). Override with `--out-dir` (e.g. `--out-dir reports` for the previous flat layout).

## Health signals to watch

1. **Startup lines** — confirm `SQLite resolved path:` matches the file you expect.
2. **`[freshness]` lines** — after each successful cycle, latest `sol_monitor_snapshots` / `spot_price_snapshots` timestamps; should advance with wall clock when ingestion is healthy.
3. **Per-cycle `OK` lines** — from `crypto_analyzer.ingest`; should list SOL/ETH/BTC spot and DEX pair summaries.
4. **`WARNING` lines** — now include `crypto_analyzer.db.writer` and `crypto_analyzer.providers.chain` (skipped writes, last-known-good, per-pair failures).
5. **`UNIVERSE_ERR`** — universe refresh failed; process **keeps running** on the last good pair list (or falls back on startup).
6. **`SOL quote missing`** — entire DEX leg skipped that cycle; investigate spot providers if frequent.
7. **429 / rate limits** — back off with larger `--interval` or `--pair-delay` before raising `universe.page_size`.

Quick DB checks (optional):

```powershell
python -c "import sqlite3; from crypto_analyzer.config import db_path; p=db_path(); c=sqlite3.connect(p); print(p); print('dex rows', c.execute('select count(*) from sol_monitor_snapshots').fetchone()[0])"
```

## When to trigger the next golden `reportv2` rerun

Minimum **calendar** and **panel** cues (tune to your hypothesis; these are practical defaults):

| Signal | Suggested minimum before rerun |
|--------|--------------------------------|
| Calendar span (1h bars) | Several **multi-week** windows of continuous materialized history (avoid short windows under ~14 days unless documented) |
| Assets in research panel | **≥ 3** non-constant return series after `filters.min_bars` (dashboard/research gating) |
| Per-asset bar count | At or above `filters.min_bars` (default 48 for 1h) for each kept name |
| Spot + DEX | Non-degenerate spot path for SOL so DEX snapshots are not systematically skipped |

Reproducibility for proof bundles: set **`CRYPTO_ANALYZER_DETERMINISTIC_TIME`** as in `docs/audit/golden_acceptance_run.md`, pass the same **`--db`**, flags, and run **Phase 3 migrations** on that file before promotion-style steps.

## Safe breadth knobs (no code changes)

- Set **`universe.enabled: true`** and use **`--universe top`**.
- Add **`universe.queries`** (or repeat **`--universe-query`**) before lowering liquidity/volume floors.
- Raise **`universe.page_size`** in small steps; increase **`--interval`** if cycles run long or providers throttle.

## Related docs

- `docs/autopolling.md` — Windows / service-style polling notes  
- `docs/audit/golden_acceptance_run.md` — deterministic reportv2 + promotion chain
