# Why This System Exists

This document states the institutional failure modes that quantitative research systems commonly exhibit, the control surfaces implemented to address them, what the system guarantees, and what it explicitly does not claim. Tone is serious and non-marketing; no hype.

---

## 1. The Failure Modes in Quant Research

The following are concrete institutional risks in research pipelines. They are stated without reference to any specific repository; they are the problems the controls are designed to mitigate.

**Data drift without identity tracking.** Datasets change over time. If there is no content-addressed identity, the same “dataset” label can refer to different underlying data across runs or promotions. Reproducibility and auditability break: you cannot assert that a promoted result was produced on the same data you later inspect.

**Silent data leakage (future rows in training).** In walk-forward or time-series splits, fitting on data that includes information from after the train period invalidates backtests. Without explicit attestation that train windows were purged of future rows and that embargo was applied, leakage can occur and go undetected.

**Non-deterministic null simulations.** Reality checks and multiple-testing adjustments rely on simulated nulls. If the RNG is not seeded from a reproducible root (tied to run and method), two “same” runs can produce different nulls and different p-values. Conclusions are then not reproducible and not auditable.

**Manual promotion without provenance.** Promoting a strategy or model to “accepted” by hand, or by updating a status field without a formal check, bypasses governance. There is no record of who promoted what, on what evidence, or whether eligibility criteria were satisfied.

**Overfitting under multiple testing.** Running many hypotheses and selecting the best without multiplicity adjustment inflates type I error. Without effective-trial adjustment, deflated Sharpe, and/or Reality Check (and optionally Romano–Wolf), reported significance is not defensible.

**Mutable artifacts without lineage.** Artifacts (bundles, RC summaries, attestations) can be overwritten or replaced. Without an append-only record of what was produced, by which run, and how artifacts relate (parent/child), you cannot reconstruct the exact inputs to a promotion decision or reproduce the pipeline.

---

## 2. Control Surfaces Implemented

For each failure mode above, the following controls are implemented.

| Failure mode | Control |
|--------------|--------|
| **Data drift without identity** | **dataset_id_v2** — Content-addressed dataset identity. Same DB content yields the same id. Promotion requires STRICT mode; FAST_DEV is for development only. |
| **Silent data leakage** | **Fold-causality attestation** — Attestation artifact records that train-only fit was enforced, purge and embargo were applied, and no future rows were used in fit. Walk-forward promotion can require this attestation. |
| **Non-deterministic nulls** | **seed_root(run_key, salt, version)** — Central RNG root derived from semantic run identity and method-specific salt; optional fold_id. Seed version is recorded; RC summary and artifacts carry seed_root/seed_version for audit. |
| **Manual promotion without provenance** | **Eligibility reports + DB triggers** — Promotion to candidate/accepted requires a linked eligibility report. Triggers block direct UPDATE of status without a valid eligibility_report_id (fail-closed). **RC/RW provenance fields** record seed, null construction, requested/actual n_sim in the report. |
| **Overfitting / multiple testing** | **Eligibility reports + gatekeeper** — Reports encode deflated Sharpe, effective trials, RC (and optionally Romano–Wolf) results. Gatekeeper can require passing eligibility and exact schema/seed versions before promotion. |
| **Mutable artifacts without lineage** | **artifact_lineage + artifact_edges** — Append-only lineage table records artifact_id, run_instance_id, run_key, dataset_id_v2, hashes, schema versions. Edges table records parent/child relations. **governance_events** — Append-only log of promotion actions (actor, candidate_id, eligibility_report_id, run_key, dataset_id_v2); UPDATE/DELETE blocked by triggers. |

**run_key vs run_instance_id** — Semantic identity (run_key) is separated from execution identity (run_instance_id). run_key is hash of config/data identity; run_instance_id identifies a single execution. This allows “same experiment” to be identified across reruns and ties seeds and lineage to semantic identity.

**Golden Acceptance Run proof** — A documented, copy-paste procedure (Golden Acceptance Run) demonstrates determinism, fail-closed promotion, trigger enforcement, and DB-only audit trace from acceptance back to eligibility, governance events, and artifact lineage.

---

## 3. What This Proves

The system is designed to deliver the following guarantees, demonstrated by the Golden Acceptance Run and supporting tests:

- **Deterministic reproducibility** — With a fixed DB and deterministic time env, the same run_key and dataset_id_v2 yield the same run_instance_id and reproducible artifacts (including RC nulls when seeded via seed_root).
- **Auditability from DB only** — From an accepted candidate, an auditor can reconstruct the full chain using only the SQLite DB: eligibility report, governance events, artifact lineage, and artifact edges. No need to rely on filesystem state.
- **Fail-closed promotion** — Promotion to accepted cannot be done by direct SQL update without a valid eligibility report; triggers enforce the link.
- **Traceability of artifacts to semantic identity** — Artifacts are tied to run_instance_id and run_key; dataset_id_v2 and seed_root tie results to dataset and RNG provenance.

---

## 4. What It Does NOT Claim

The following are explicitly out of scope:

- **Statistical certification under all DGPs** — Calibration and RC/RW are guards and sanity checks, not a guarantee of validity for arbitrary data-generating processes.
- **Distributed governance** — Single-writer, local-first. No distributed locking or multi-writer audit guarantees.
- **Execution platform** — Research-only; no live execution, order routing, or broker integration.
- **Multi-user concurrent system** — Concurrency and access control are not design goals; the audit trail assumes a single writer.

These boundaries keep the design precise and honest about what the controls achieve.

---

## See also

- [Golden acceptance run — proof bundle](golden_acceptance_run.md)
- [Methods & implementation alignment](methods_implementation_alignment.md)
