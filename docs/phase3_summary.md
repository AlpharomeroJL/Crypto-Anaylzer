# Phase 3 — Productization / Institutional Defensibility — Summary

## Concise change summary

Phase 3 turns the repo into a cleanly separable, plugin-capable, institutionally auditable research validation platform:

- **Package boundaries**: Added `crypto_analyzer/core/` (run identity only so far), `crypto_analyzer/governance/` (run identity + promotion entrypoint), `crypto_analyzer/store/` (backend interface, SQLite/DuckDB), `crypto_analyzer/plugins/` (versioned plugin API). Run-identity code moved from root `governance.py` into `core/run_identity.py`; root `governance` is now the package that re-exports run identity and `evaluate_and_record` / `promote`.

- **Governance**: Single entrypoint `governance.promote.evaluate_and_record` and `governance.promote.promote`; all evaluate/promote actions logged to append-only `governance_events` when the table exists.

- **Lineage**: New tables `artifact_lineage` and `artifact_edges` (append-only, triggers block UPDATE/DELETE). Research pipeline records lineage when `conn` or `db_path` is provided; `db/lineage.py` and `db/governance_events.py` provide persistence.

- **Plugins**: `plugins/api.py` defines `PLUGIN_API_VERSION`, `TRANSFORM_PLUGIN_VERSION`, `STAT_PROCEDURE_PLUGIN_VERSION`, `TransformPlugin`, `StatProcedurePlugin`, and an explicit registry; plugin manifest can be stored in bundle meta and lineage.

- **Store**: `store/backend.py` defines `Backend`; `sqlite_backend.py` and `duckdb_backend.py` implement it. Lineage and governance always write to SQLite; DuckDB is optional for analytics read/compute.

- **Version discipline**: Gatekeeper already required `engine_version` and `config_version` for candidate/accepted; tests assert that missing versions block eligibility.

- **CLI**: `research_report_v2` supports `--backend sqlite|duckdb` (default `sqlite`).

---

## Migrations added

All in `crypto_analyzer/db/migrations_phase3.py`:

| Version | Name | Description |
|--------|------|-------------|
| 11 | `2026_02_governance_events` | Append-only `governance_events` table + triggers (no UPDATE/DELETE). |
| 12 | `2026_02_artifact_lineage` | `artifact_lineage` table + append-only triggers. |
| 13 | `2026_02_artifact_edges` | `artifact_edges` table + append-only triggers; FK to `artifact_lineage`. |

Existing Phase 1/2 tables and migrations are unchanged.

---

## New modules

| Path | Purpose |
|------|--------|
| `crypto_analyzer/core/__init__.py` | Core package (no governance/store/cli deps). |
| `crypto_analyzer/core/run_identity.py` | Run identity, manifests, `get_git_commit`, `stable_run_id`, etc. (moved from root `governance.py`). |
| `crypto_analyzer/governance/__init__.py` | Re-exports run identity + `evaluate_and_record`, `promote`. |
| `crypto_analyzer/governance/promote.py` | Single entrypoint: `evaluate_and_record`, `promote`; logs to `governance_events`. |
| `crypto_analyzer/store/__init__.py` | Exports `Backend`, `get_backend`, `set_backend`. |
| `crypto_analyzer/store/backend.py` | Abstract `Backend`: `read_table`, `write_artifact_lineage`, `write_artifact_edge`, `query_analytics`. |
| `crypto_analyzer/store/sqlite_backend.py` | SQLite backend (default). |
| `crypto_analyzer/store/duckdb_backend.py` | DuckDB backend for read/analytics; lineage still via SQLite conn. |
| `crypto_analyzer/plugins/__init__.py` | Plugin package. |
| `crypto_analyzer/plugins/api.py` | Plugin API versions, `TransformPlugin`, `StatProcedurePlugin`, registry. |
| `crypto_analyzer/db/lineage.py` | `write_artifact_lineage`, `write_artifact_edge`, `lineage_tables_exist`. |
| `crypto_analyzer/db/governance_events.py` | `append_governance_event`, `governance_events_table_exists`. |

**Removed**: `crypto_analyzer/governance.py` (replaced by `governance/` package).

---

## How to run the Phase 3 verification suite

```powershell
# From repo root, with venv activated
.venv\Scripts\activate

# All tests (including Phase 3)
python -m pytest tests/ -q --tb=short

# Phase 3–specific tests only
python -m pytest tests/test_no_illegal_imports.py tests/test_plugin_registry.py tests/test_plugin_contract_versions.py tests/test_plugin_determinism_seeded.py tests/test_governance_event_log_append_only.py tests/test_no_bypass_promotion_paths.py tests/test_artifact_lineage_append_only.py tests/test_artifact_lineage_written.py tests/test_lineage_reproducibility_same_run_key_same_hashes.py tests/test_backend_equivalence_small_case.py tests/test_duckdb_backend_does_not_change_governance_state.py tests/test_gatekeeper_requires_versions_and_seed_version.py -v --tb=short

# Lint
ruff check .
ruff format .
```

**What to look for**: All tests pass; no illegal imports; governance events and lineage triggers block mutation; gatekeeper rejects when versions missing.

---

## Institutional audit story: trace an accepted result end-to-end

You can answer **“Which inputs + configs + engine versions produced this artifact hash?”** in a single DB (SQLite), without reading files.

1. **Start from an accepted candidate**  
   In `promotion_candidates`, take a row with `status = 'accepted'` and its `eligibility_report_id`.

2. **Eligibility report**  
   In `eligibility_reports`, the row with that `eligibility_report_id` gives:
   - `run_key`, `run_instance_id`, `dataset_id_v2`, `engine_version`, `config_version`.

3. **Governance events**  
   In `governance_events`, filter by that `candidate_id` and `eligibility_report_id` to see the sequence of actions (`evaluate`, `promote`) and actors.

4. **Artifact lineage**  
   In `artifact_lineage`, filter by `run_key` and/or `dataset_id_v2` (and optionally `run_instance_id`) to get all artifact rows for that run:
   - `artifact_id` (sha256 hex), `artifact_type`, `relative_path`, `sha256`, `created_utc`, `engine_version`, `config_version`, `schema_versions_json`, `plugin_manifest_json`.

5. **Edges**  
   In `artifact_edges`, use `child_artifact_id` / `parent_artifact_id` and `relation` to see how artifacts (e.g. `hashes.json`) derive from others (`manifest`, `rc_summary`, `fold_causality_attestation`, etc.).

**Single-query example (by run_key):**

```sql
SELECT al.artifact_id, al.run_key, al.dataset_id_v2, al.artifact_type, al.relative_path, al.sha256, al.engine_version, al.config_version, al.schema_versions_json, al.plugin_manifest_json
FROM artifact_lineage al
WHERE al.run_key = :run_key
ORDER BY al.created_utc;
```

**End-to-end chain:**  
`dataset_id_v2` → (runs with that dataset) → `run_key` → fold attestation / RC/RW artifacts referenced in bundle and eligibility → `eligibility_reports` row → `promotion_candidates.status = 'accepted'` → `governance_events` (evaluate/promote) → `artifact_lineage` + `artifact_edges` for every artifact hash produced by that run.

No execution or live trading was added. Phase 1 and Phase 2 invariants and test suite are preserved; changes are additive and migration-safe.
