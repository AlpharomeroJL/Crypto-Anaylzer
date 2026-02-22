# Golden acceptance run — proof bundle

This document provides copy-paste steps to demonstrate the system’s institutional guarantees end-to-end on Windows PowerShell, using public endpoints only (no API keys). DuckDB is optional; the proof uses SQLite only.

---

## A. Goal and guarantees

**What this run proves**

- **Deterministic dataset identity** — `dataset_id_v2` is content-addressed; same DB content yields the same id.
- **Deterministic run identity** — `run_key` (semantic) and `run_instance_id` (execution); reproducible under `CRYPTO_ANALYZER_DETERMINISTIC_TIME=1`.
- **Seeded RNG provenance** — `seed_root`, `seed_version` in artifacts and RC summary when Reality Check is enabled.
- **Fold-causality attestation** — When walk-forward is used, attestation artifact is required for promotion.
- **RC/RW provenance** — When enabled, RC summary records seed, null construction, requested/actual n_sim.
- **Fail-closed promotion** — Candidate/accepted require a passing eligibility report; DB triggers block direct `UPDATE` of status without a linked report.
- **Append-only governance** — `governance_events` and lineage tables are append-only; triggers block UPDATE/DELETE.
- **DB-only audit trace** — From an accepted candidate you can query eligibility, governance events, and artifact lineage without reading files.

**What this run does not prove**

- Statistical validity under all DGPs.
- Distributed concurrency or multi-writer safety.
- Live execution or trading (research-only; no orders).
- Correctness of third-party providers beyond what the tests cover.

---

## B. Prerequisites

- **Python** 3.10+ (3.14 used in development).
- **Venv** at repo root: `.venv\Scripts\activate`.
- **Install**: `pip install -e ".[dev]"` (or `pip install -r requirements.txt`).
- **No API keys** — ingestion uses public CEX/DEX endpoints only.

**Environment (for deterministic run)**

- `CRYPTO_ANALYZER_DETERMINISTIC_TIME=1` — makes `run_id` and run_key-derived seeds stable across runs.
- `CRYPTO_ANALYZER_DB_PATH` — optional; default `reports/crypto_analyzer.db`.

---

## C. Golden run commands (PowerShell)

All commands from repo root. Use a dedicated DB path for a clean proof (e.g. a temp path or `reports/golden_proof.db`).

### Minimal proof (no walk-forward, RC optional)

Uses existing or minimal data; no Reality Check required for promotion; fastest path to “accepted” + trigger + audit trace.

```powershell
# 1) Optional: fresh DB (or use existing reports/crypto_analyzer.db after migrations)
$env:CRYPTO_ANALYZER_DB_PATH = "reports\golden_proof.db"
New-Item -ItemType Directory -Path reports -Force | Out-Null
if (-not (Test-Path $env:CRYPTO_ANALYZER_DB_PATH)) {
    .\.venv\Scripts\python.exe -c "
from pathlib import Path
from crypto_analyzer.store.sqlite_session import sqlite_conn
from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.db.migrations_phase3 import run_migrations_phase3
p = Path('reports/golden_proof.db')
with sqlite_conn(p) as c:
    run_migrations(c, p)
    run_migrations_phase3(c, p)
print('DB created and Phase 3 migrations applied')
"
}

# 2) Optional: minimal ingest + materialize (if DB is empty and you want real bars)
# .\scripts\run.ps1 universe-poll --universe --universe-chain solana --interval 60
# .\scripts\run.ps1 materialize --freq 1h

# 3) Deterministic reportv2 (same config + DB → same run_id)
$env:CRYPTO_ANALYZER_DETERMINISTIC_TIME = "1"
.\scripts\run.ps1 reportv2 --freq 1h --out-dir reports --db $env:CRYPTO_ANALYZER_DB_PATH --hypothesis "golden proof"

# 4) Get run_id from latest manifest (used in create)
$runId = (Get-Content (Get-ChildItem reports\csv\manifest_*.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName | ConvertFrom-Json).run_instance_id
if (-not $runId) { $runId = (Get-ChildItem reports\csv\validation_bundle_*.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1).BaseName -replace 'validation_bundle_[^_]+_[^_]+_', '' -replace '\.json$', '' }
Write-Host "Run ID for create: $runId"

# 5) Create promotion candidate (signal/horizon must match report; adjust if needed)
$bundlePath = Get-ChildItem reports\csv\validation_bundle_*_$runId.json -ErrorAction SilentlyContinue | Select-Object -First 1
$cid = .\.venv\Scripts\python.exe cli/promotion.py create --from-run $runId --signal "clean_momentum" --horizon 1 --db $env:CRYPTO_ANALYZER_DB_PATH --bundle-path $bundlePath.FullName 2>&1 | Select-Object -Last 1
$cid = $cid.Trim()
Write-Host "Candidate ID: $cid"

# 6) Evaluate and promote to accepted (no --require-rc for minimal proof)
.\.venv\Scripts\python.exe cli/promotion.py evaluate --id $cid --db $env:CRYPTO_ANALYZER_DB_PATH

# 7) Demonstrate trigger: direct SQL update without eligibility_report_id is blocked
.\.venv\Scripts\python.exe -c "
import sqlite3, os
db = os.environ.get('CRYPTO_ANALYZER_DB_PATH', 'reports/crypto_analyzer.db')
conn = sqlite3.connect(db)
cur = conn.execute(\"SELECT candidate_id FROM promotion_candidates WHERE status = 'accepted' LIMIT 1\")
row = cur.fetchone()
if row:
    try:
        conn.execute(\"UPDATE promotion_candidates SET status = 'candidate', eligibility_report_id = NULL WHERE candidate_id = ?\", (row[0],))
        conn.commit()
        print('UNEXPECTED: trigger did not fire')
    except (sqlite3.IntegrityError, sqlite3.OperationalError) as e:
        print('Trigger correctly blocked direct UPDATE:', str(e)[:80])
else:
    print('No accepted candidate in DB; skip trigger check')
conn.close()
"

# 8) Emit DB-only audit trace (see Section D for SQL and helper)
.\.venv\Scripts\python.exe cli/audit_trace.py trace-acceptance --db $env:CRYPTO_ANALYZER_DB_PATH --candidate-id $cid
```

### Full proof (walk-forward strict + RC + RW enabled)

- Use reportv2 with `--reality-check` and `--execution-evidence`; optionally enable Romano–Wolf and walk-forward.
- Same steps as above, but:
  - Set `CRYPTO_ANALYZER_ENABLE_ROMANOWOLF=1` if you want RW in RC.
  - Run reportv2 with `--reality-check` and `--execution-evidence`; create candidate with `--rc-summary-path` and `--execution-evidence-path` pointing to the generated files.
  - Evaluate with `--require-rc` (and optionally `--require-exec`).

```powershell
$env:CRYPTO_ANALYZER_DETERMINISTIC_TIME = "1"
# Optional: $env:CRYPTO_ANALYZER_ENABLE_ROMANOWOLF = "1"
.\scripts\run.ps1 reportv2 --freq 1h --out-dir reports --db $env:CRYPTO_ANALYZER_DB_PATH --reality-check --execution-evidence --hypothesis "full proof"
# Then create with --rc-summary-path and --execution-evidence-path; evaluate with --require-rc
```

---

## D. DB-only audit trace: acceptance → provenance

These SQL queries (and the `trace-acceptance` CLI) show how to reconstruct the full chain from an accepted candidate using only the SQLite DB.

### 1. Find accepted candidate and join eligibility report

```sql
SELECT
  pc.candidate_id,
  pc.status,
  pc.run_id,
  pc.eligibility_report_id,
  pc.evidence_json,
  er.run_key,
  er.run_instance_id,
  er.dataset_id_v2,
  er.engine_version,
  er.config_version,
  er.passed,
  er.level,
  er.computed_at_utc
FROM promotion_candidates pc
LEFT JOIN eligibility_reports er ON er.eligibility_report_id = pc.eligibility_report_id
WHERE pc.status = 'accepted'
LIMIT 1;
```

`seed_version` and schema versions live in bundle meta and in `artifact_lineage.schema_versions_json`, not in `eligibility_reports`.

### 2. Governance events (append-only)

```sql
SELECT event_id, timestamp, actor, action, candidate_id, eligibility_report_id, run_key, dataset_id_v2
FROM governance_events
WHERE candidate_id = :candidate_id
ORDER BY event_id;
```

### 3. Artifact lineage for the run

```sql
SELECT artifact_id, run_instance_id, run_key, dataset_id_v2, artifact_type, relative_path, sha256, created_utc, engine_version, config_version, schema_versions_json
FROM artifact_lineage
WHERE run_instance_id = :run_instance_id
ORDER BY created_utc;
```

Use `run_instance_id` from the candidate row or from `evidence_json` / eligibility report.

### 4. Artifact edges (parent/child graph)

```sql
SELECT child_artifact_id, parent_artifact_id, relation
FROM artifact_edges
WHERE child_artifact_id IN (SELECT artifact_id FROM artifact_lineage WHERE run_instance_id = :run_instance_id)
   OR parent_artifact_id IN (SELECT artifact_id FROM artifact_lineage WHERE run_instance_id = :run_instance_id)
ORDER BY child_artifact_id, relation;
```

### Invoking the read-only audit helper

The repo provides a read-only CLI that calls `crypto_analyzer.governance.audit.trace_acceptance`:

```powershell
.\.venv\Scripts\python.exe cli/audit_trace.py trace-acceptance --db reports\crypto_analyzer.db --candidate-id <CANDIDATE_ID>
```

Optional: `--json` to dump machine-readable trace (eligibility_report_id, governance_events, artifact_lineage). No writes, no migrations, no promotion actions.

---

## E. Determinism check

- **Rerun report step** with the same DB and deterministic time; compare manifest or bundle hashes.
- Set `CRYPTO_ANALYZER_DETERMINISTIC_TIME=1` and run reportv2 twice; the determinism test asserts byte-identical outputs:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_reportv2_deterministic_rerun.py -q --tb=short
```

- RC RNG determinism:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_reality_check_deterministic.py tests/test_reality_check_rng_determinism.py -q --tb=short
```

---

## F. Known limitations

- **Statistical certification** — Calibration and RC/RW are guards, not full certification under all DGPs.
- **Concurrency** — Single-writer, local-first; no distributed locking or multi-writer audit guarantees.
- **Execution/trading** — No live execution, order routing, or broker integration.
- **Data scope** — Public endpoints only; no authenticated or proprietary feeds.
- **DuckDB** — Optional analytics backend; governance and lineage are SQLite-only; proof does not depend on DuckDB.
