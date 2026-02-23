# A Deterministic Validation Control Plane for Quant Research

This document describes the validation control plane implemented in the Crypto-Analyzer research platform: a layered system of deterministic identity, statistical defenses, governance, lineage, and proof artifacts designed to make research results auditable and promotion decisions non-bypassable. The tone is institutional; the goal is clarity for auditors and risk committees, not marketing.

---

## 1. Threat Model

The control plane explicitly addresses the following threats.

| Threat | Description |
| ------ | ----------- |
| **Data snooping** | Repeated trials, signal mining, or horizon scanning inflate false discoveries unless corrected. Uncorrected p-values are not sufficient for promotion. |
| **Implicit multiple testing** | Many signals, horizons, or variants are tested; family-wise or FDR control is required so that “discoveries” are not merely the best of many random outcomes. |
| **Reproducibility drift** | Same logical inputs (dataset, config, engine) must yield the same identifiers and, under deterministic settings, the same outputs. Timestamps, paths, or environment must not silently change run identity or artifact hashes. |
| **Promotion without controls** | A candidate must not be elevated to candidate or accepted status without a passing eligibility evaluation. Direct SQL or API updates that bypass the gatekeeper are unacceptable. |
| **Artifact mutation** | Outputs (validation bundles, RC summaries, attestations) must be immutable once referenced by promotion. Tampering or silent overwrites must be detectable via content hashes and append-only lineage. |
| **Audit impossibility** | An auditor must be able to reconstruct why a result was accepted using only the database: which report passed, which artifacts were used, and what governance actions occurred, without relying on external logs or mutable files. |

The design is fail-closed: if a gate cannot be satisfied (e.g. missing attestation, STRICT dataset hash, or schema version mismatch), promotion is blocked rather than relaxed.

---

## 2. Deterministic Identity Layer

Stable, content-addressed identifiers ensure that “same experiment” is well-defined and reproducible.

**dataset_id_v2**  
Content-addressed hash of the logical content of allowlisted SQLite tables (e.g. `bars_*`, spot snapshots, universe allowlist). Rows are hashed in a canonical order (primary key, deterministic keys, then time/rowid). A single cell change produces a different `dataset_id_v2`. Modes STRICT and FAST_DEV exist; **promotion requires STRICT**. VACUUM or other operations that do not change row content leave the id unchanged. This prevents “same run, different data” from being treated as the same experiment.

**run_key**  
Deterministic hash of the *semantic* run payload: dataset_id_v2, config (e.g. signal, horizon, factor params), engine_version, config_version. Timestamps, paths, and run_instance_id are **excluded**. Thus two runs with the same inputs and code versions yield the same run_key; only semantically meaningful changes change it. Used for cache invalidation, deduplication, and tying artifacts to a logical run.

**run_instance_id**  
Execution instance identifier (e.g. from the run manifest). It can differ across executions even when run_key is the same (e.g. two runs of the same pipeline). Used to group artifacts and to join with lineage and eligibility reports.

**seed_root**  
A 64-bit unsigned integer derived from `run_key`, a component-specific **salt** (e.g. for Reality Check nulls, CSCV splits, fold splits), an optional fold_id, and a **version**. Formula: SHA-256 of `run_key|salt|version` (with fold_id normalized as `fold:{id}` when present); first 8 bytes as big-endian integer. Same (run_key, salt, fold_id, version) yields the same seed across process runs. All stochastic procedures (bootstrap, RC nulls, CSCV permutations) must use randomness derived from this layer so that reruns are reproducible and “same run_key, different engine” is explainable via version.

**Schema versions**  
Artifacts carry explicit schema version fields (e.g. `validation_bundle_schema_version`, `rc_summary_schema_version`, `fold_causality_attestation_schema_version`, seed derivation version). The gatekeeper requires exact version match for promotion. This prevents silent schema drift from making old artifacts uninterpretable or from being accepted under a new contract. Versions are defined in code (e.g. `crypto_analyzer/contracts/schema_versions.py`) and referenced by the promotion gating logic.

---

## 3. Statistical Defense Layer

The stack provides multiple testing control, deflated performance metrics, overfitting checks, and calibration. These are **defenses**, not full statistical certification under all data-generating processes.

**BH/BY (FDR)**  
Benjamini–Hochberg and Benjamini–Yekutieli procedures adjust p-values for false discovery rate. BH assumes independence or positive dependence; BY is valid under arbitrary dependence and is strictly more conservative. Adjusted p-values and discovery sets are produced per family (e.g. signals in the run). Promotion policy can require that discoveries survive a chosen level (e.g. q = 5%).

**DSR + Neff**  
Deflated Sharpe Ratio (DSR) corrects for multiple trials and non-normality. The expected maximum Sharpe under the null is approximated; DSR and its p-value are computed from the observed Sharpe, that expectation, and the variance of the Sharpe estimator. **Effective number of trials (Neff)** is computed from the eigenvalue structure of the strategy return correlation matrix ($N_{\mathrm{eff}} = (\sum \lambda_i)^2 / \sum \lambda_i^2$). When `--n-trials auto` is used, reportv2 uses Neff so that correlated strategies do not overcount as independent trials. Artifacts record `n_trials_user`, `n_trials_eff_eigen`, `n_trials_used`, and related keys for audit.

**CSCV PBO (note deviation)**  
Combinatorial Symmetric Cross-Validation Probability of Backtest Overfitting: data is split into S blocks; for each of a set of train/test partitions, the in-sample “winner” is ranked out-of-sample; PBO is the fraction of splits where that rank is below median ($\lambda < 0$). **Implementation note:** When the number of possible partitions exceeds `max_splits`, the implementation uses **randomly sampled** partitions (with a seed) rather than full enumeration. This is deterministic for a fixed seed but may increase the variance of the PBO estimate compared to full enumeration. Documented as a known deviation in the methods implementation alignment audit; reviewers should be aware when interpreting `pbo_cscv` and related artifacts.

**Reality Check**  
White-style Reality Check: observed maximum statistic over the hypothesis set; null distribution via bootstrap (e.g. stationary bootstrap) with the **same** resampling indices across hypotheses. Romano–Wolf stepdown (opt-in) provides family-wise adjusted p-values. RC summary records `seed_root`, component salt, null construction spec, requested/actual n_sim; the gatekeeper can require RC and can block if actual_n_sim is below a threshold (e.g. 95% of requested) so that underpowered nulls do not pass.

**HAC**  
Newey–West long-run variance for mean inference (e.g. mean return or mean IC). Lag order can be auto (e.g. $\lfloor 4(n/100)^{2/9} \rfloor$ capped by n/3) or user-supplied. Minimum sample size (e.g. n ≥ 30) is enforced; below that, HAC is skipped and `hac_skipped_reason` is set with null t/p. This is inference on the **mean**, not full finite-sample Sharpe.

**Calibration harness**  
CI runs calibration experiments (e.g. Type I, FDR) using synthetic or null data. The harness uses `rng_for(run_key, SALT_CALIBRATION)` when run_key is set. Calibration is intended to catch egregious miscalibration; tolerances are wide and it is not a full statistical certification.

**Reference alignment audit for known deviations**  
The repo maintains a methods implementation alignment document that maps each method to code locations, artifact keys, and **known deviations** (benign convention differences vs material correctness/interpretation risks). CSCV PBO split sampling and DSR variance convention are examples. Auditors and reviewers should use this document to interpret artifacts and to assess whether deviations are acceptable for their use case.

---

## 4. Governance Layer

Governance ensures that promotion is only possible through evaluated eligibility and that all actions are logged.

**eligibility_reports**  
Each evaluation of a promotion candidate for a given level (exploratory, candidate, accepted) produces an eligibility report: passed/not passed, blockers_json, warnings_json, and provenance (run_key, run_instance_id, dataset_id_v2, engine_version, config_version). Reports are stored in the `eligibility_reports` table. Referenced reports (by candidate/accepted rows) cannot be deleted or have their passed/level fields updated—triggers enforce immutability so that evidence cannot be altered after the fact.

**Promotion states**  
Candidates live in `promotion_candidates` with status: exploratory → candidate → accepted. Transitions to candidate or accepted are **only** valid when the row has an `eligibility_report_id` pointing to a report that (1) passed and (2) has level equal to the target status. No other path to candidate/accepted is allowed.

**Fail-closed triggers**  
Database triggers on `promotion_candidates` block INSERT/UPDATE that would set status to candidate or accepted without a valid, passing eligibility report at the matching level. Direct SQL (e.g. `UPDATE promotion_candidates SET status = 'accepted'`) is rejected. Promotion must go through the designated API (evaluate_eligibility, then promote), which writes the report and then updates status with the correct eligibility_report_id.

**Append-only governance_events**  
Every evaluate and promote action is appended to `governance_events` (timestamp, actor, action, candidate_id, eligibility_report_id, run_key, dataset_id_v2, optional artifact_refs). UPDATE and DELETE on this table are **forbidden** by triggers. The log is append-only so that the history of who did what and when cannot be rewritten.

---

## 5. Lineage Layer

Lineage ties accepted results to the exact artifacts and versions that produced them.

**artifact_lineage**  
Each recorded artifact (validation bundle, RC summary, fold attestation, etc.) is inserted as a row: artifact_id, run_instance_id, run_key, dataset_id_v2, artifact_type, relative_path, **sha256**, created_utc, engine_version, config_version, schema_versions_json, plugin_manifest_json. Rows are append-only (triggers block UPDATE/DELETE). The sha256 field stores the content hash of the artifact file so that tampering or replacement can be detected by recomputing the hash.

**artifact_edges**  
A second table records directed edges between artifacts: child_artifact_id, parent_artifact_id, relation (e.g. derived_from, uses_null, uses_folds, uses_transforms, uses_config). This forms a graph from outputs back to inputs and configs. Edges are append-only. Together with artifact_lineage, an auditor can walk from an accepted run to all inputs and dependent artifacts.

**SHA256 integrity**  
Artifacts referenced in lineage have their file content hashed (e.g. SHA-256). The hash is stored in `artifact_lineage`. Verification is possible by re-reading the file and comparing to the stored sha256. Same run_key and deterministic pipeline should yield the same hashes on rerun (enforced by determinism tests).

**DB-only audit trace**  
The full chain from an accepted candidate to eligibility report, governance events, and artifact lineage (and edges) is queryable using only the SQLite database. No need to read external log files or mutable manifests to reconstruct “why was this accepted?” The `trace-acceptance` CLI (and underlying `trace_acceptance` helper) return eligibility_report_id, governance_events list, and artifact_lineage rows for a given candidate_id.

---

## 6. Proof Artifact

The **Golden Acceptance Run** is the executable evidence that the control plane behaves as specified. It is documented in `docs/audit/golden_acceptance_run.md`.

It provides copy-paste PowerShell steps (or equivalent) to:

1. Create a DB and apply Phase 3 migrations (eligibility_reports, promotion triggers, governance_events, artifact_lineage, artifact_edges).
2. Run a deterministic report (e.g. with `CRYPTO_ANALYZER_DETERMINISTIC_TIME=1`), obtain run_id and validation bundle path.
3. Create a promotion candidate and attach the bundle.
4. Evaluate eligibility and promote to accepted via the official API.
5. Run the DB-only audit trace (trace-acceptance) to show eligibility → governance → lineage.
6. Demonstrate that a direct SQL UPDATE attempting to set status to candidate/accepted without a valid eligibility_report_id is **blocked** by the trigger.

Thus the Golden run proves in one flow: deterministic dataset and run identity, seeded RNG provenance (when RC/artifacts include seed_root), fail-closed promotion, append-only governance and lineage, and the possibility of a DB-only audit. It does **not** prove statistical validity under all DGPs, concurrency safety, or correctness of external data providers.

---

## 7. Limitations & Future Extensions

**Transparency**  
The following limitations are acknowledged.

- **Statistical certification**  
  BH/BY, DSR, Neff, RC/RW, CSCV PBO, and HAC are applied as specified in the methods docs and alignment audit, but no guarantee is made that they are sufficient for every DGP or use case. Calibration harness has wide tolerances; it is a sanity check, not a full certification.

- **CSCV PBO**  
  Random-sampled splits when $\binom{S}{S/2} > \mathrm{max\_splits}$ (or the implementation’s equivalent) may increase PBO estimate variance relative to full enumeration. This is a documented deviation; interpretation should account for it.

- **Concurrency**  
  The system is single-writer, local-first. No distributed locking or multi-writer audit guarantees. Concurrent promotion or lineage writes are not designed for.

- **Execution and data scope**  
  No live trading or order routing. Data is from public endpoints only; no authenticated or proprietary feeds. Capacity curves and execution evidence are research-side proxies.

- **DuckDB**  
  Optional analytics backend; governance, lineage, and promotion are SQLite-only. The Golden run and audit trace do not depend on DuckDB.

**Future extensions (non-committal)**  
Possible directions include: optional full enumeration for CSCV when computationally feasible; tighter calibration targets and more null DGPs; multi-writer or replicated audit logs with defined consistency guarantees; and extended artifact types (e.g. model weights) with the same lineage and SHA256 discipline. None of these are committed; they are noted for institutional readers who need to assess roadmap and risk.

---

*This whitepaper aligns with the implementation as of the audit and methods alignment documents. For code locations, artifact keys, and known deviations, see `docs/audit/methods_implementation_alignment.md` and `docs/methods_and_limits.md`.*
