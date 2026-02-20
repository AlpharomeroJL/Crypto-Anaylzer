# Phase 3 Slice 5: Promotion workflow (exploratory → candidate → accepted) — alignment

**Canonical spec:** [master_architecture_spec.md](master_architecture_spec.md), [schema_plan.md](components/schema_plan.md), [interfaces.md](components/interfaces.md), [testing_acceptance.md](components/testing_acceptance.md), [performance_scale.md](components/performance_scale.md), [phased_execution.md](components/phased_execution.md).

## Scope

- Persisted promotion state in SQLite (promotion_candidates, promotion_events).
- Service layer: create/list/get/update status, evaluate_and_record using gating.evaluate_candidate.
- Streamlit: Promotion page (list, view details, evaluate, manual status + reason).
- CLI: promotion list, promotion create, promotion evaluate (opt-in; no default behavior change).
- Targeted caching: RC null simulations keyed by family_id + rc config + dataset_id + git_commit; cache manifest (key → artifact sha256); no-cache override.

## Tables and columns

### promotion_candidates

| Column            | Type    | Notes |
|-------------------|---------|--------|
| candidate_id      | TEXT PK | Stable id (e.g. hash of run_id+signal+horizon+created_at or UUID). |
| created_at_utc    | TEXT    | ISO UTC. |
| status            | TEXT    | exploratory | candidate | accepted | rejected. |
| dataset_id        | TEXT    | From run. |
| run_id            | TEXT    | Report run. |
| family_id         | TEXT    | Nullable; set when RC used. |
| signal_name       | TEXT    | |
| horizon           | INTEGER | Primary horizon. |
| estimator         | TEXT    | Nullable. |
| config_hash       | TEXT    | Reproducibility. |
| git_commit        | TEXT    | Reproducibility. |
| notes             | TEXT    | Nullable. |
| evidence_json     | TEXT    | JSON: artifact paths, metrics snapshot, rc_summary path, regime paths. |

**Indexes:** status, dataset_id, signal_name, created_at_utc (for list/filters).

### promotion_events (append-only audit)

| Column       | Type | Notes |
|--------------|------|--------|
| event_id     | INTEGER PK | Auto-increment or rowid. |
| candidate_id  | TEXT | FK to promotion_candidates. |
| ts_utc       | TEXT | ISO UTC. |
| event_type   | TEXT | e.g. created, status_change, evaluated. |
| payload_json | TEXT | Reason, old/new status, decision snapshot. |

**Index:** candidate_id for per-candidate history.

## Migration strategy

- Add to **Phase 3** migrations only: `run_migrations_phase3` (same runner as regime_runs/regime_states).
- New migrations: 004 promotion_candidates, 005 promotion_events.
- Version numbers: 4 and 5 in schema_migrations_phase3.
- Idempotent: CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS.
- Promotion tables are opt-in: applied when caller runs Phase 3 migrations (e.g. when enabling regimes or explicitly enabling promotion workflow). No change to default run_migrations().

## Service APIs

- **store_sqlite:** create_candidate(conn, payload) → candidate_id; update_status(conn, candidate_id, status, reason); record_event(conn, candidate_id, event_type, payload); list_candidates(conn, status=None, dataset_id=None, signal_name=None, limit=100); get_candidate(conn, candidate_id) → row dict or None.
- **service:** evaluate_and_record(conn, candidate_id, thresholds: ThresholdConfig, bundle_or_path, regime_summary_df=None, rc_summary=None) → PromotionDecision; loads bundle if path given; calls gating.evaluate_candidate; updates candidate status; records event with decision + reasons + snapshot.
- Deterministic serialization: evidence_json via write_json_sorted-style canonical JSON (sorted keys, stable floats).

## UI actions (Streamlit)

- List candidates with filters (status, dataset_id, signal_name).
- View candidate details: evidence paths, RC summary path, regime paths, metrics snapshot.
- Button “Evaluate”: call evaluate_and_record with current thresholds (sidebar options for require_rc, require_regime); show decision and record event.
- Manual status change: dropdown + reason text; record_event then update_status.

All UI actions go through the promotion service/store; no inline business logic.

## Caching keys and invalidation

- **RC null cache:** Key = (family_id, rc_metric, rc_horizon, rc_n_sim, rc_seed, rc_method, rc_avg_block_length, dataset_id, git_commit). Value: null_max distribution (e.g. CSV or binary). Stored on disk with manifest; manifest row: key_hash → artifact_path, sha256.
- **Invalidation:** dataset_id or git_commit or any RC config change → new key → recompute. No silent reuse without key match.
- **No-cache override:** Env CRYPTO_ANALYZER_NO_CACHE=1 or CLI --no-cache skips cache read/write.
- **Factor runs:** Existing idempotency by factor_run_id; optional “skip compute if rowcounts match” only when safe (document in code). Not required for Slice 5 minimum.
- **Regime cache:** Optional; key by regime_run_id (already stable). Defer if not obviously expensive.

## Tests and acceptance

- **Migrations:** Apply run_migrations_phase3 idempotently; tables and indexes exist; column list matches spec.
- **Store:** create_candidate returns id; list_candidates filters; get_candidate; update_status; record_event append-only (event_id increasing per candidate).
- **Service:** evaluate_and_record with fixed bundle + thresholds → deterministic decision; status and event updated.
- **E2E:** Create candidate from fixture bundle (optional RC artifact path in evidence); evaluate with require_reality_check or require_regime; assert stored decision and event log and status transition.
- **UI:** Import + route exists (Promotion page in sidebar); no crash on load (smoke).
- **Default behavior:** reportv2 and backtest unchanged when promotion not used; verify script passes with promotion disabled.

## Registry / experiment linkage

- Candidates store run_id, dataset_id, config_hash, git_commit so they can be linked to experiment registry rows if present. No mandatory FK to experiments table (registry may be in separate DB).
