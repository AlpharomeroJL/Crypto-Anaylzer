# Architecture

## Architecture Overview

Crypto-Anaylzer is a **deterministic research validation platform**: local-first, SQLite-backed. It governs whether a research result is eligible for promotion (candidate → accepted) and maintains an auditable chain from accepted results back to dataset identity, run identity, fold causality, and artifacts. Flow: **Ingestion** (CEX/DEX providers) → **Materialization** (OHLCV bars) → **Modeling** (factors, signals, inference) → **Presentation** (dashboard/API/CLI). Research validation adds: dataset hashing, run identity, seeded RNG, fold attestation, eligibility gating, governance events, and artifact lineage. SQLite is the single source of truth for governance and lineage; execution and trading are out of scope.

---

## Core Invariants

- **Dataset identity is content-addressed** — `dataset_id_v2` is a deterministic hash of allowlisted research tables (schema + ordered rows, canonical NaN). It changes iff logical content of in-scope tables changes. Promotion requires STRICT mode.
- **Run identity is semantic (run_key) vs execution (run_instance_id)** — `run_key` = hash of semantic payload (dataset_id_v2, config, versions); excludes timestamps/paths. `run_instance_id` = single execution id (e.g. manifest run_id). Same config + dataset → same run_key across runs.
- **All randomness derives from seed_root** — `seed_root(run_key, salt, fold_id=None, version)` → SHA-256 → 64-bit seed. Single canonical RNG module; no process-dependent `hash()`. `seed_version` stored in artifacts.
- **Promotion is fail-closed** — Candidate/accepted require a passing eligibility report; DB triggers block INSERT/UPDATE without a linked `eligibility_report_id` and `passed=1` at the same level. Referenced eligibility reports cannot be deleted or have passed/level changed.
- **Governance events are append-only** — `governance_events` table; triggers block UPDATE and DELETE. All evaluate/promote actions are logged.
- **Lineage is stored in authoritative SQLite** — `artifact_lineage` (artifact_id, run_key, dataset_id_v2, sha256, …) and `artifact_edges` (child, parent, relation) are append-only in SQLite. DuckDB is optional read-only analytics; lineage never written to DuckDB.

---

## System Layers

- **core** — Identity + seeding + context. `run_identity.py`: `compute_run_key`, `build_run_identity`, `RunIdentity`. `rng` / `core/seeding.py`: `seed_root`, `rng_for`, component salts, `SEED_ROOT_VERSION`. `context.py`: `RunContext`, `ExecContext`; `require_for_promotion()`. No imports from governance, store, or CLI.
- **data** — Dataset hashing + loaders. `dataset_v2.py`: content-addressed `compute_dataset_id_v2`, `get_dataset_id_v2`; scope allowlist, STRICT/FAST_DEV. Bar/research data loaders and research-universe access.
- **stats** — Inference + multiple testing + calibration. BH/BY (FDR), Reality Check (max-statistic bootstrap), Romano–Wolf stepdown; calibration harness (Type I, FDR, RC, RW, CSCV). All stochastic paths use `rng_for(run_key, salt)`; RC/RW provenance (seed_root, null_construction_spec, actual_n_sim) in artifacts for gating.
- **pipeline** — Folds + transforms + attest. Research pipeline: walk-forward folds (purge/embargo, train-only fit), transforms, validation bundle emission. Fold causality attestation (schema version, purge_embargo_asof, train_only_fit_enforced) required for promotion when walk-forward used. Writes artifact_lineage/edges when conn/db_path provided.
- **governance** — Gates + promotion + audit. `promotion/gating.py`: `evaluate_eligibility(bundle, level, rc_summary)` → EligibilityReport; fail-closed for candidate/accepted (STRICT dataset, run_key, versions, fold attestation when WF, RC/RW when enabled). `promotion/store_sqlite.py`: promotion_candidates, promotion_events. `governance_events` append. `audit.py`: `trace_acceptance(conn, candidate_id)` → AuditTrace.
- **artifacts** — Registry + contracts. Validation bundle (IC series, decay, turnover, paths), schema versions (validation_bundle, rc_summary, fold_causality_attestation, etc.). Artifact types and paths; contract versions enforced by gatekeeper.
- **cli** — Thin orchestration. reportv2, poll, streamlit, promotion commands, audit_trace. Parses args, resolves db_path/backend, invokes pipeline/governance/store; no business logic for gating or identity.

---

## Trust Boundary

- **core + governance** define the **research control plane**: run identity, seed derivation, dataset hashing, eligibility evaluation, fail-closed promotion triggers, governance event log, and audit trace. Code in core and governance must be correct and dependency-minimal for trust.
- **cli** is **orchestration only**: it calls core, data, pipeline, governance, and store. It does not implement gating, identity, or seeding; it must not bypass evaluate_eligibility or promotion store/triggers.
- **Execution and trading are not part of the trust boundary.** The platform certifies research eligibility and auditability; it does not execute orders, hold API keys, or guarantee profitability.

---

## Audit Path

Bullet diagram for tracing an accepted candidate back to evidence:

- **accepted candidate** (promotion_candidates.status = 'accepted', eligibility_report_id)
- → **eligibility_report** (eligibility_reports row: passed, level, run_key, dataset_id_v2, engine_version, config_version)
- → **governance_events** (event_id, timestamp, actor, action, candidate_id, eligibility_report_id; evaluate → promote)
- → **artifact_lineage** (artifact_id, run_key, dataset_id_v2, sha256, artifact_type, relative_path, … for that run_instance_id)
- → **artifact_edges** (child_artifact_id, parent_artifact_id, relation: derived_from, uses_null, uses_folds, …)
- → **validation_bundle** (per-signal bundle paths and hashes referenced in evidence; schema_version, run_key, dataset_id_v2, seed_version)
- → **fold attestation + rc_summary** (fold_causality_attestation: purge/embargo, train_only_fit; rc_summary: seed_root, actual_n_sim, null_construction_spec; both required for candidate/accepted when applicable)

Trace order: candidate_id → eligibility_report_id → governance_events (chronological) → run_instance_id → artifact_lineage → artifact_edges → validation_bundle and attestation/rc artifacts.
