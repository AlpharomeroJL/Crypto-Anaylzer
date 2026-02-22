# Validation Control Plane — Audit Narrative

**Document type:** Structured audit memo  
**Audience:** Quant infra / research platform reviewers  
**Scope:** What the system is, what it enforces, and what it does not guarantee.

---

## 1. Executive summary

Crypto-Anaylzer provides a **deterministic research validation control plane**: it governs whether a research result is eligible for promotion (candidate/accepted) and maintains an auditable chain from accepted results back to dataset identity, run identity, fold causality, and artifacts. The system prevents statistical illusion and enforces reproducibility, causality, and governance at the database and gatekeeper layers. It does **not** execute trades, hold API keys, or certify that promoted signals are profitable. Core mechanisms: content-addressed dataset identity (`dataset_id_v2`), semantic and execution run identity (`run_key`, `run_instance_id`), versioned deterministic seed derivation, fold-causality attestation (purge/embargo, train-only fit), eligibility reports with fail-closed DB triggers, append-only governance events, and append-only artifact lineage. SQLite is the single authoritative store for governance and lineage; DuckDB is an optional read-only analytics backend.

---

## 2. System objective

- **Prevent statistical illusion** — Avoid silent data drift, run identity ambiguity, non-reproducible randomness, multiple-testing/selection bias, and leakage via transforms or walk-forward.
- **Enforce reproducibility** — Same inputs and version pins yield the same run_key and deterministic seeds; artifact hashes and lineage allow verification.
- **Enforce causality** — Walk-forward splits with purge/embargo; fit only on train; attestation artifact attests to what was applied.
- **Enforce governance** — No candidate or accepted status without a passing eligibility report; evidence is immutable when referenced; all transitions logged in an append-only event log.

---

## 3. Threat model (explicit)

The control plane is designed to mitigate the following failure modes:

| Threat | Mitigation |
|--------|------------|
| **Silent data drift** (e.g. cache hit with changed data) | `dataset_id_v2` is a content-addressed hash of allowlisted tables; one row or schema change changes the id. Promotion requires STRICT mode. |
| **Run identity ambiguity** | `run_key` (semantic) and `run_instance_id` (execution) are explicit; run_key excludes timestamps/paths; same config + dataset → same run_key. |
| **Stochastic non-reproducibility** | Seeds derived via `seed_root(run_key, salt, version)`; `seed_version` in artifacts; no use of process-dependent hash(). |
| **Multiple testing / selection bias** | BH/BY (FDR), optional RC (max-statistic bootstrap), optional Romano–Wolf stepdown; calibration harness runs Type I/FDR/RC/RW/CSCV checks in CI (guards, not full certification). |
| **Leakage via transforms / walk-forward** | Fold causality: purge/embargo, train-only fit; attestation with schema version; gatekeeper requires valid attestation when walk-forward used. |
| **Governance bypass** | Fail-closed: candidate/accepted require eligibility_report_id; DB triggers block INSERT/UPDATE without a linked passing report at the same level; eligibility reports referenced by candidate/accepted cannot be deleted or have passed/level changed. |
| **Artifact provenance ambiguity** | `artifact_lineage` (artifact_id, run_key, dataset_id_v2, sha256, …) and `artifact_edges` (child, parent, relation); append-only; trace from accepted → run → inputs/configs/artifacts. |

---

## 4. Design overview

### 4.1 dataset_id_v2 (content-addressed dataset identity)

- **Scope:** Allowlisted research-visible tables only (e.g. `spot_price_snapshots`, `sol_monitor_snapshots`, `bars_1h`, `bars_15min`, `bars_5min`, `universe_allowlist`). Excludes governance/registry tables (experiments, promotion_*, regime_*, sweep_*, schema_*).
- **Logic:** Per-table: schema signature (PRAGMA table_info) + ordered row content. Ordering: PK columns if present; else deterministic keys if configured; else timestamp column + rowid; else rowid. Rows serialized in canonical form (NaN normalized); SHA-256 over concatenated table contributions; first 16 hex chars = `dataset_id_v2`.
- **Modes:** STRICT (full content; required for promotion); FAST_DEV (faster, may trade completeness for speed).
- **Invariant:** `dataset_id_v2` changes iff canonicalized logical content of in-scope tables changes (e.g. VACUUM with no data change leaves it unchanged).

### 4.2 run_key and run_instance_id

- **run_key:** Deterministic hash of *semantic* payload: dataset_id_v2, factor/config, signals, horizons, RC/RW toggles, version pins (engine_version, config_version, research_spec_version, …). Explicitly **excluded:** ts_utc, created_utc, timestamp, out_dir, output_dir, path, paths. Same config + same dataset → same run_key across runs.
- **run_instance_id:** Identifies a single execution (e.g. manifest run_id); may include timestamp for uniqueness. Same run_key can have many run_instance_ids.
- **RunContext:** Pipelines receive RunContext(run_key, run_instance_id, dataset_id_v2, engine_version, config_version, seed_version, schema_versions); required for promotion and for stochastic procedures.

### 4.3 Seed derivation (salted, versioned)

- **Formula:** `seed_root(run_key, salt=salt, fold_id=optional, version=SEED_ROOT_VERSION)`. Payload `run_key|salt_effective|version` (fold_id normalized as `fold:{id}` when present) → SHA-256 → first 8 bytes as big-endian uint64 → mod 2^63.
- **Salts:** Single canonical module (`crypto_analyzer.rng`): e.g. SALT_RC_NULL, SALT_CSCV_SPLITS, SALT_FOLD_SPLITS, SALT_CALIBRATION, SALT_STATIONARY_BOOTSTRAP, etc. All stochastic procedures use `rng_for(run_key, salt)` or equivalent.
- **Versioning:** `SEED_ROOT_VERSION`; stored as `seed_version` in artifacts (validation bundle, RC summary, fold attestation). Changing the hashing scheme or salt set requires bumping version so “same run_key, different nulls” is explainable.

### 4.4 Fold causality and attestation

- **Splits:** Walk-forward with configurable purge_gap_bars and embargo_bars; train and test do not overlap; purge shrinks train_end; embargo pushes test_start later.
- **Fit:** Train-only fit; no future rows in fit.
- **Attestation:** `build_fold_causality_attestation` produces a dict with schema version, run identity, purge_embargo_asof, train_only_fit_enforced, purge_applied, embargo_applied, no_future_rows_in_fit. Stored as fold_causality_attestation.json in validation bundle; meta carries fold_causality_attestation_schema_version and inline attestation for gatekeeper.
- **Gatekeeper:** For candidate/accepted, when walk_forward_used (or fold_causality_attestation_path present), evaluate_eligibility requires valid attestation (schema version match and validate_attestation(att) passes).

### 4.5 Eligibility reports and fail-closed triggers

- **evaluate_eligibility(bundle, level, rc_summary):** Returns EligibilityReport(passed, level, blockers, warnings, run_key, run_instance_id, dataset_id_v2, …). Exploratory: pass with warnings. Candidate/Accepted: fail-closed (STRICT dataset_id_v2, run_key, engine_version, config_version, fold attestation when WF used, RC/RW contract when enabled, validation_bundle_contract).
- **Persistence:** Report written to `eligibility_reports` (eligibility_report_id, candidate_id, level, passed, blockers_json, warnings_json, run_key, dataset_id_v2, …).
- **Promotion:** promote_to_candidate / promote_to_accepted set promotion_candidates.status and eligibility_report_id. **Triggers:** BEFORE UPDATE/INSERT on promotion_candidates WHEN status IN ('candidate','accepted') require eligibility_report_id IS NOT NULL and (SELECT passed FROM eligibility_reports …) = 1 and (SELECT level …) = NEW.status; else RAISE(ABORT).
- **Immutability:** Triggers on eligibility_reports block DELETE when the row is referenced by any candidate/accepted; block UPDATE of passed/level when referenced.

### 4.6 Governance event log

- **Table:** governance_events (event_id, timestamp, actor, action, candidate_id, eligibility_report_id, run_key, dataset_id_v2, artifact_refs_json). Append-only: triggers block UPDATE and DELETE.
- **Actions:** evaluate, promote (and optionally reject). Every evaluate_and_record / promote call appends when the table exists.

### 4.7 Artifact lineage and edges

- **artifact_lineage:** artifact_id (PK), run_instance_id, run_key, dataset_id_v2, artifact_type, relative_path, sha256, created_utc, engine_version, config_version, schema_versions_json, plugin_manifest_json. Append-only (triggers block UPDATE/DELETE).
- **artifact_edges:** child_artifact_id, parent_artifact_id, relation (e.g. derived_from, uses_null, uses_folds, uses_transforms, uses_config). FK to artifact_lineage; append-only.
- **Usage:** Pipeline writes lineage when conn/db_path provided; audit trace: accepted → candidate_id → eligibility_report_id → run → artifact_lineage rows for that run → artifact_edges for graph.

### 4.8 Backend separation

- **SQLite:** Authoritative for governance (promotion_candidates, eligibility_reports, governance_events) and lineage (artifact_lineage, artifact_edges). All promotion and lineage writes go to SQLite.
- **DuckDB:** Optional; used for read_table/query_analytics when a DuckDB path is provided. Lineage and governance **never** written to DuckDB; DuckDBBackend.write_artifact_lineage uses the provided SQLite conn only.

---

## 5. Statistical stack (honest)

| Component | Purpose | What is empirically checked | Known limitations / assumptions |
|-----------|---------|-----------------------------|-----------------------------------|
| **BH / BY** | FDR control for discovery | Calibration smoke/full (Type I, FDR) in calibration_*.py | BH assumes independence/positive dependence; BY more conservative under dependence. |
| **Reality Check (RC)** | Max-statistic bootstrap, data-snooping | RC calibration (null rejection rate, p-value distribution) | Bootstrap null assumes stationarity; regime breaks can distort. |
| **Romano–Wolf (RW)** | Stepdown FWER | RW calibration tests | Same bootstrap/null assumptions as RC. |
| **CSCV PBO** | Probability of backtest overfitting | CSCV smoke (pbo in [0,1], not all same) | Block stationarity; PBO measures ranking instability, not significance. |
| **Bootstrap** | Stationary / block bootstrap for CIs and nulls | Reproducibility (fixed seed → same samples); marginal smoke | Block length choice; stationarity. |
| **HAC** | Newey–West LRV for mean inference | HAC calibration skeleton (optional) | n ≥ 30 for t/p; otherwise skipped with reason. |

Calibration tests are **CI-safe guards** (fast smoke + optional slow full). They are not a full statistical certification of the methods under all data-generating processes.

---

## 6. Governance and auditability

### 6.1 Fail-closed promotion path

- **exploratory → candidate:** Create candidate row (status=exploratory); call evaluate_eligibility(bundle, "candidate", …); persist report to eligibility_reports; call promote_to_candidate(candidate_id, eligibility_report_id). Trigger ensures eligibility_report_id is set and report passed=1 and level='candidate'.
- **candidate → accepted:** evaluate_eligibility(bundle, "accepted", …); persist report; promote_to_accepted(candidate_id, eligibility_report_id). Trigger ensures report passed=1 and level='accepted'.

Direct UPDATE of promotion_candidates.status to candidate/accepted without a valid eligibility_report_id is blocked by the DB.

### 6.2 What constitutes “promotion evidence”

- A row in eligibility_reports with passed=1 and level matching the target status.
- For candidate/accepted: bundle meta must satisfy STRICT dataset_id_v2, run_key, engine_version, config_version, fold_causality when walk-forward used, RC/RW when enabled; validation_bundle_contract (schema_version, seed_version, etc.) must pass.

### 6.3 Tracing an accepted result in the DB (without reading files)

1. **promotion_candidates** — Filter status='accepted'; get candidate_id, eligibility_report_id.
2. **eligibility_reports** — eligibility_report_id → run_key, run_instance_id, dataset_id_v2, passed, level, blockers_json, computed_at_utc.
3. **governance_events** — Filter by candidate_id (and optionally eligibility_report_id); order by event_id; see sequence of evaluate/promote and actors.
4. **artifact_lineage** — Filter by run_key or run_instance_id (from eligibility_reports or governance_events); get all artifact_id, artifact_type, sha256, created_utc for that run.
5. **artifact_edges** — Join on child_artifact_id/parent_artifact_id to walk graph (e.g. validation_bundle → fold_causality_attestation, rc_summary, etc.).

---

## 7. Reproducibility guarantees (explicit)

### 7.1 What is deterministic (under same environment and versions)

- **dataset_id_v2:** Same logical content and scope → same id. STRICT mode required for promotion.
- **run_key:** Same semantic payload (excluding excluded keys) → same run_key.
- **Seeds:** Same (run_key, salt, version) → same seed_root and thus same RNG stream for RC, bootstrap, CSCV, fold splits, etc.
- **Fold splits:** Same data length and purge/embargo config and seed → same splits.
- **Artifact hashes:** Same inputs and code → same bundle contents and SHA256 (when deterministic_time and seeds used).

### 7.2 Version fields required for reproducibility

- **seed_version** in bundle meta, RC summary, fold attestation (must match SEED_ROOT_VERSION or be explicitly versioned).
- **fold_causality_attestation_schema_version** when walk-forward used.
- **rc_summary_schema_version** when RC/RW used.
- **engine_version, config_version** (and for accepted, research_spec_version recommended).

### 7.3 What breaks reproducibility (and how versions prevent silent breakage)

- **Changing hashing scope or algorithm for dataset_id_v2** — New dataset_id_v2; run_key changes; no silent reuse of old cache.
- **Changing run_key payload (e.g. adding a key that is not excluded)** — run_key changes; seeds change.
- **Changing seed derivation (salt set or encoding)** — Bump SEED_ROOT_VERSION and seed_version in artifacts; old artifacts remain interpretable (“different seed_version”).
- **Changing fold or RC schema** — Schema versions in attestation and rc_summary; gatekeeper rejects mismatches.

---

## 8. Remaining gaps / future hardening

- **Multi-user concurrency** — No locking or conflict resolution for concurrent promotion or lineage writes; single-writer or process-level coordination assumed.
- **Distributed compute** — Single-node only; no distributed run orchestration or distributed lineage.
- **Observability** — No built-in metrics/APM for promotion latency or lineage write volume; logging is standard.
- **Full statistical certification** — Calibration tests are regression guards; formal certification of Type I/FDR under all DGPs is out of scope.

The system does **not** propose or implement execution, order routing, or live trading.

---

*End of audit narrative.*
