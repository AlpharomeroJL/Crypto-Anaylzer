# Extension surface

This document lists planned extension points for the Crypto Quantitative Research Platform. For each, we describe **current state**, **required refactor** (high-level), **risk level**, and that the extension **does not break invariants**.

Invariants referenced below are those documented in `docs/design.md`, `docs/architecture.md`, and `docs/audit/golden_acceptance_run.md` (e.g. single source of truth, idempotent migrations, provenance on every write, append-only governance, fail-closed promotion, fold-causality attestation when walk-forward used).

---

## 1. Backend abstraction (SQLite → Postgres)

| Aspect | Description |
|--------|-------------|
| **Current state** | SQLite is the single source of truth for core data: `db/migrations.py` (core + v2), `db/writer.py`, `db/health.py`, `read_api`, ingest, materialize, promotion store, and artifact lineage all use a single `db_path`. The **experiment store** is already abstracted: `experiment_store.py` offers `SQLiteExperimentStore` (default) and `PostgresExperimentStore` (when `EXPERIMENT_DB_DSN` is set). The **store** layer has a `Backend` interface for analytics read/compute (SQLite + DuckDB); lineage writes always go to the provided SQLite connection. |
| **Required refactor** | Introduce a core DB abstraction: connection factory and migration runner per backend (SQLite vs Postgres). Writer and read_api (and ingest, materialize, promotion store) consume this abstraction rather than raw `sqlite3` + path. Migrations become backend-aware (e.g. Postgres-compatible DDL). Optionally keep governance/lineage on SQLite as the authority, or extend schema/migrations for Postgres so lineage lives in the same DB as core. |
| **Risk level** | **High** — touches migrations, writer, all readers, and many call sites; schema and SQL dialect differences (e.g. AUTOINCREMENT vs SERIAL, type names) must be handled. |
| **Does not break invariants** | Single source of truth is preserved by routing all reads/writes through the abstraction. Idempotent migrations and provenance on every write remain; append-only governance and auditability are preserved (same triggers or equivalent constraints on the chosen backend). |

---

## 2. Artifact storage abstraction

| Aspect | Description |
|--------|-------------|
| **Current state** | `crypto_analyzer.artifacts` uses the local filesystem only: `ensure_dir`, `write_df_csv`, `write_json`, `write_json_sorted`, SHA256 hashing, `snapshot_outputs`, timestamped filenames. Output paths are config- or report-directory based; no abstract “artifact store” interface. |
| **Required refactor** | Define an `ArtifactStore` interface (e.g. `get(key)`, `put(key, content)`, optional `content_hash`). Implement `LocalArtifactStore` wrapping current file I/O. Callers (report pipelines, promotion service, research pipeline) accept an optional store or use a default. Later: S3/GCS implementations with same interface. |
| **Risk level** | **Medium** — many call sites pass paths and write directly; refactor must preserve deterministic hashes and path stability for lineage and bundle contracts. |
| **Does not break invariants** | Deterministic hashes (SHA256) and “no overwrite of immutable artifacts” remain. Artifact paths and hashes in `artifact_lineage` and validation bundles stay consistent; lineage and governance events still reference the same logical artifacts. |

---

## 3. Promotion workflow API

| Aspect | Description |
|--------|-------------|
| **Current state** | Promotion is in-process only: `promotion/service.py` (`evaluate_and_record`), `promotion/store_sqlite.py`, `promotion/gating.py`, and CLI `cli/promotion.py`. There is no HTTP API for listing candidates, evaluating, or promoting; the FastAPI `crypto_analyzer.api` exposes `/health`, `/latest/allowlist`, `/experiments/*`, `/metrics/*`, `/reports/latest` but not promotion. |
| **Required refactor** | Add API routes (e.g. `/promotion/candidates`, `/promotion/evaluate`, `/promotion/promote`) that delegate to the existing promotion service and store. Optional: idempotency keys and auth for production use. |
| **Risk level** | **Low–Medium** — new surface; existing promotion logic and DB layer unchanged. Risk is in auth, input validation, and rate limiting. |
| **Does not break invariants** | Audit trail (eligibility_report, governance_events, artifact_lineage) is unchanged; fail-closed gating and fold-causality attestation requirements remain enforced inside the existing service. API becomes another caller of the same code path. |

---

## 4. Multi-tenant isolation

| Aspect | Description |
|--------|-------------|
| **Current state** | No tenancy: single `db_path`, single experiment store, no `tenant_id` (or equivalent) in schema. All data is global to the instance. |
| **Required refactor** | Introduce tenant context (e.g. `tenant_id` or namespace) in config and in schema (per-table tenant column or separate DB per tenant). Scope ingest, materialize, read_api, experiment store, and promotion store by tenant. Ensure no cross-tenant reads/writes. |
| **Risk level** | **High** — pervasive: migrations, writer, readers, experiment store, promotion store, API, and CLI all must be tenant-aware. Default behavior must remain “single tenant” when tenant is not set. |
| **Does not break invariants** | Single source of truth per tenant; no cross-tenant data leakage. Idempotent migrations, provenance, append-only governance, and fail-closed promotion apply within each tenant. When only one tenant is configured, behavior matches current single-tenant invariants. |

---

## 5. Policy engine

| Aspect | Description |
|--------|-------------|
| **Current state** | Promotion gating is implemented in `promotion/gating.py`: fixed thresholds and rules (IC mean, t-stat, p-value, Reality Check, regime robustness, execution evidence, fold-causality attestation when walk-forward used). No pluggable “policy” abstraction; rules are hardcoded. |
| **Required refactor** | Define a policy interface (e.g. `evaluate_candidate(meta, evidence) -> allow/deny + reasons`). Wrap current gating logic in a default policy implementation. Allow registration of additional policies or overrides (e.g. config-driven thresholds or external policy service) while keeping a single decision path for audit. |
| **Risk level** | **Medium** — gating is on the critical path for promotion; misconfiguration or bug can open the fail-closed guarantee. |
| **Does not break invariants** | Eligibility report and governance events still record the same decision and reasons. Fail-closed semantics and attestation requirements (fold_causality when walk-forward) are preserved; the policy engine becomes the single place that produces the decision, with full audit trail. |

---

## 6. Pluggable stats procedures

| Aspect | Description |
|--------|-------------|
| **Current state** | `crypto_analyzer.plugins` exposes `StatProcedurePlugin` and a registry (`register_stat_procedure`, `get_plugin_registry`). Contract: `run(bundle, context) -> results + artifacts`; deterministic when seeded. Built-in stats (e.g. Reality Check, RW, CSCV) are not necessarily registered as plugins; pipeline and reportv2 call them directly. |
| **Required refactor** | Register built-in stats as plugins; have pipeline/research report discover and run procedures by name from config. Allow external procedures (e.g. custom Python or versioned contracts) via the same registry. Ensure plugin manifest is recorded in lineage. |
| **Risk level** | **Low–Medium** — plugin API already exists; refactor is mostly wiring and config. Risk is in contract stability and determinism of third-party procedures. |
| **Does not break invariants** | Deterministic, seeded behavior and validation-bundle contract are unchanged. Plugin manifest in artifact lineage and run identity preserves reproducibility; no bypass of existing validation or attestation requirements. |

---

## 7. CI integration

| Aspect | Description |
|--------|-------------|
| **Current state** | `.github/workflows/verify.yml` runs on push/PR: checkout, Python venv, install deps, diagram tools, and `.\scripts\run.ps1 verify` (doctor, pytest, ruff, diagrams). No artifact upload, no deployment, no reporting to external systems. |
| **Required refactor** | Optional: upload artifacts (e.g. coverage, report bundles); optional webhook or API call to report run results; optional “promotion from CI” (e.g. tag or comment triggers promote). Keep verify as the single definition of “pass”; additive only. |
| **Risk level** | **Low** — additive; existing verify job and scripts unchanged. Risk is in secrets handling and scope of “promotion from CI” (must use same promotion service and invariants). |
| **Does not break invariants** | Verify remains the authoritative pass/fail. No live trading or execution; research-only boundary preserved. Any promotion from CI uses the same promotion service and store, so audit trail and fail-closed gating are unchanged. |

---

## 8. External attestations (signing)

| Aspect | Description |
|--------|-------------|
| **Current state** | Fold-causality attestation is a JSON blob: `fold_causality/attestation.py` builds and validates structure (`build_fold_causality_attestation`, `validate_attestation`); no cryptographic signing. Run identity is in `core/run_identity.py`. Attestation is required for candidate/accepted when walk-forward is used; validation is schema + checks only. |
| **Required refactor** | Add optional signing: sign attestation payload (or digest) with a configured key; verify on load when signature is present. Keep unsigned attestations valid for local use; require signature only when “external” or “promotion from CI” is desired. Document key management and verification path. |
| **Risk level** | **Medium** — key management, verification in promotion gating and API, and backward compatibility for existing unsigned artifacts. |
| **Does not break invariants** | Attestation schema version and validation logic are unchanged; signing is additive. Fold-causality semantics (train-only fit, purge, embargo, no future rows in fit) remain enforced by existing checks. Unsigned attestations continue to satisfy current promotion rules when signing is not required. |

---

## Summary table

| Extension surface              | Risk level   | Invariants preserved |
|--------------------------------|-------------|----------------------|
| Backend (SQLite → Postgres)    | High        | Yes                  |
| Artifact storage abstraction   | Medium      | Yes                  |
| Promotion workflow API         | Low–Medium  | Yes                  |
| Multi-tenant isolation         | High        | Yes (per tenant)     |
| Policy engine                  | Medium      | Yes                  |
| Pluggable stats procedures     | Low–Medium  | Yes                  |
| CI integration                 | Low         | Yes                  |
| External attestations (signing)| Medium      | Yes                  |
