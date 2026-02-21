# Phase 3 Slice 5 — Promotion Workflow + UI + Performance (PR Checklist)

> This PR completes Phase 3 of the architecture roadmap.
> It is governance-level and must satisfy reproducibility, leakage, and determinism invariants.
> No default behavior may change unless explicitly documented and justified.

---

## When opening this PR

**Recommended PR title**

Phase 3 Slice 5 — Promotion Workflow + UI + Deterministic Caching

**At the top of the PR description, include:**

Spec reference:
- docs/spec/master_architecture_spec.md
- docs/spec/phase3_promotion_slice5_alignment.md
- docs/spec/phase3_slice5_pr_template.md

**Before submitting the PR, fill in:**
- Files changed
- Migration versions (e.g., 004 promotion_candidates, 005 promotion_events)
- Example candidate row (sanitized)
- Example promotion_events entries
- Cache key example (showing full key components)
- Output of `.\scripts\run.ps1 verify` (PASS)

---

## Summary
- [ ] Implements persisted promotion workflow: exploratory → candidate → accepted/rejected
- [ ] Adds Streamlit Promotion UI (minimal) + CLI commands (minimal)
- [ ] Adds additive SQLite schema + versioned Phase 3 migrations (opt-in only)
- [ ] Adds targeted deterministic caching (bounded scope)
- [ ] Keeps default behavior unchanged (opt-in, no auto-promotion)

## Spec alignment (required)
- [ ] `docs/spec/phase3_promotion_slice5_alignment.md` exists and matches implementation
- [ ] `docs/spec/implementation_ledger.md` updated with Slice 5 rows (tests + evidence)
- [ ] `docs/spec/components/phased_execution.md` updated (Slice 5 checked only if green)

## Non-negotiables / invariants
### Opt-in behavior
- [ ] No new defaults changed in report/backtest/scan pipelines
- [ ] Promotion workflow is not triggered unless explicitly invoked (UI action or CLI command)
- [ ] Phase 3 migrations are not applied by default (only via explicit `run_migrations_phase3` opt-in)

### Reproducibility + auditability
- [ ] Every candidate stores:
  - [ ] dataset_id
  - [ ] run_id
  - [ ] signal_name + horizon (+ estimator if applicable)
  - [ ] config_hash
  - [ ] git_commit
  - [ ] family_id (nullable) + RC config/rc_p_value if used
  - [ ] artifact paths (ValidationBundle JSON, RC summary, regime summaries if present)
- [ ] Audit log is append-only (promotion_events), no mutation of past events
- [ ] Evidence JSON is written with stable serialization (sorted keys, stable float rounding)

### Leakage + statistical discipline
- [ ] If configured to require Reality Check: cannot accept without rc_p_value <= threshold
- [ ] If configured to require regime robustness: cannot accept if worst regime fails threshold / insufficient regime coverage
- [ ] No smoothing-in-test violations (regimes remain filter-only)

## DB schema + migrations (SQLite)
### Tables (additive)
- [ ] `promotion_candidates` table created with indexes (status, dataset_id, signal_name, created_at_utc)
- [ ] `promotion_events` table created with FK to candidate, indexed by candidate_id, ts_utc
- [ ] Migrations are idempotent (`CREATE TABLE/INDEX IF NOT EXISTS`)
- [ ] Backup/restore strategy matches migrations_v2/migrations_phase3 behavior

### Migration tests
- [ ] New DB → apply phase3 migrations (opt-in) → tables exist
- [ ] Re-run migrations → no duplicate rows / no errors
- [ ] Failure restore test (if applicable): DB contents restored on exception

## Promotion service layer (no UI deps)
- [ ] `promotion/store_sqlite.py` provides:
  - [ ] create_candidate
  - [ ] get_candidate
  - [ ] list_candidates (filters)
  - [ ] update_status
  - [ ] record_event
- [ ] `promotion/service.py` provides:
  - [ ] evaluate_and_record(candidate_id, thresholds, rc_summary?, regime_summary?, …)
  - [ ] deterministic PromotionDecision + recorded event payload

## Streamlit UI (minimal, usable)
- [ ] Promotion page/tab exists
- [ ] Can list candidates with filters
- [ ] Can open candidate details (links/paths to bundle + artifacts)
- [ ] Can run evaluation and persist decision + reasons + metrics snapshot
- [ ] Can manually update status with reason (records event)

## CLI (minimal)
- [ ] `promotion list` works (filters optional)
- [ ] `promotion create --from-run <run_id> --signal <name> --horizon <h>` works
- [ ] `promotion evaluate --id <candidate_id> [--require-rc] [--require-regime-robustness]` works
- [ ] CLI is deterministic: same inputs → same stored decision (given same artifacts)

## Caching (targeted, deterministic)
- [ ] Cache keys include:
  - [ ] dataset_id
  - [ ] config_hash
  - [ ] git_commit
  - [ ] family_id (if RC)
  - [ ] rc config (metric/horizon/n_sim/seed/method/avg_block_length)
- [ ] Cache storage is deterministic and verifiable (manifest + sha256)
- [ ] Cache can be disabled (no-cache flag or env)
- [ ] Cache invalidation documented (key changes imply miss; no silent reuse)

## Artifacts + outputs
- [ ] Promotion evaluation writes or references:
  - [ ] ValidationBundle JSON (relative paths)
  - [ ] RC summary JSON (if used)
  - [ ] regime-conditioned artifacts (if used)
  - [ ] PromotionDecision snapshot (stored in DB and/or as JSON artifact)
- [ ] Artifacts are stable serialized (sorted keys; stable CSV ordering)

## Tests (required)
### Unit tests
- [ ] Promotion store CRUD + filters
- [ ] Promotion events append-only behavior
- [ ] Promotion evaluate_candidate deterministic
- [ ] Require Reality Check gating accept/reject (already in Slice 4; extend to service flow)
- [ ] Require regime robustness gating accept/reject (from Slice 2; extend to service flow)

### Integration tests
- [ ] End-to-end: create candidate → evaluate → status transition → event recorded
- [ ] With RC enabled: consumes rc_summary artifact and enforces threshold
- [ ] With regimes enabled: consumes regime artifacts and enforces robustness

### Determinism tests
- [ ] Same candidate + same artifacts + deterministic time → identical decision snapshot and stored evidence hash

## Commands run (paste output or note PASS)
- [ ] `.\scripts\run.ps1 verify` (doctor → pytest → ruff → research-only → diagrams) ✅
- [ ] Optional: `.\scripts\run.ps1 reportv2 ...` (baseline unchanged) ✅
- [ ] Optional: Promotion CLI smoke: create/list/evaluate ✅

## Evidence (required)
- [ ] Link to ledger rows in `docs/spec/implementation_ledger.md`
- [ ] Example candidate row (sanitized) showing stored repro metadata
- [ ] Example event log entries for evaluate + status change
- [ ] Cache manifest example (key + sha256)

## Deferred / out of scope (must remain out)
- [x] ~~Full Romano–Wolf stepdown implementation~~ — **Done:** RW implemented (opt-in via CRYPTO_ANALYZER_ENABLE_ROMANOWOLF=1). See methods_and_limits.md §9.
- [ ] Full sweep registry UX redesign
- [ ] Major performance refactors (vectorization of rolling OLS, etc.)
- [ ] Tick-level execution modeling
