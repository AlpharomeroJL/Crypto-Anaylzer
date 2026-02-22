# Product Thesis: Research Governance as Infrastructure

This document states the product thesis for the Crypto Quantitative Research Platform: treating **research governance as infrastructure** rather than an afterthought. It explains the problem, the current state of the industry, what this system enables, possible evolutions, and why local-first design is a strength.

---

## 1. The Problem

Quantitative research lacks **deterministic governance**.

- **Promotion is informal.** Strategies or models move to “accepted” via spreadsheets, Slack decisions, or ad-hoc SQL. There is no enforceable link between “what passed” and “what was promoted.”
- **Audit trails are weak.** Who promoted what, on what evidence, and with which dataset or seed is not reliably recorded. Reproducibility and compliance become reactive exercises.
- **Compliance and reproducibility are reactive.** When regulators or internal audit ask “prove this result,” teams scramble to reconstruct history from emails and mutable files. There is no single, authoritative chain from acceptance back to data and method.

The result: research that cannot be confidently audited, reproduced, or defended under scrutiny.

---

## 2. Current State of the World

In practice, quant research today runs on:

- **Spreadsheets** — Status, promotion decisions, and run metadata live in Excel or Google Sheets. No content-addressed identity; “same run” is ambiguous.
- **Ad-hoc backtests** — Scripts and notebooks are run manually or via one-off automation. Seeds and data versions are often undocumented; reruns may not match.
- **Manual review** — Humans decide promotion without a formal gate. There is no requirement that an eligibility report or attestation exist before status changes.
- **Mutable artifacts** — Bundles, summaries, and attestations are overwritten or replaced. There is no append-only lineage of what was produced by which run and how artifacts relate.

This state is the baseline. The platform is designed to replace it with deterministic, DB-anchored governance—without requiring cloud or multi-user infrastructure from day one.

---

## 3. What This Enables

When research governance is implemented as infrastructure:

- **Deterministic research identity** — Runs are identified by content-addressed `run_key` and `dataset_id_v2`. Same config and data yield the same identity; seeds are derived from semantic identity so null simulations and results are reproducible.
- **Enforceable promotion gates** — Promotion to candidate or accepted requires a linked eligibility report. DB triggers block direct `UPDATE` of status without a valid `eligibility_report_id` (fail-closed). No back door.
- **DB-level audit trace** — From an accepted candidate, an auditor can reconstruct the full chain using only the SQLite database: eligibility report, governance events, artifact lineage, and artifact edges. No dependence on filesystem or external logs.
- **Immutable artifact lineage** — Append-only lineage and edges record what was produced, by which run, and parent/child relationships. Artifacts are tied to `run_instance_id`, `run_key`, and `dataset_id_v2`; attestations (e.g. fold-causality) are part of the same trace.

These properties turn governance from a manual, reactive process into a **verifiable, deterministic pipeline** that can be audited and reproduced from the database alone.

---

## 4. Extension Surface

The current system is **single-node, SQLite-first, by design.** One writer, one database, local-first. The following are **possible evolutions**, not commitments; they describe an extension surface if requirements grow.

| Evolution | Description |
|-----------|-------------|
| **Postgres backend** | Optional Postgres for teams that need concurrent read scaling or existing DWH integration. SQLite remains the reference and default; migration path would preserve schema and governance semantics. |
| **S3 artifact storage** | Artifact blobs (bundles, attestations) could be stored in S3 with content-addressed keys; DB would retain lineage and hashes, pointing to external storage. |
| **Multi-user governance** | Multiple researchers with distinct identities; `governance_events` and promotion policies could include `actor_id` and role. Would require authentication and authorization layer. |
| **Web review UI** | Browser-based review of eligibility reports, artifact lineage, and promotion history—read-only over the same DB or a replicated view. |
| **Signed eligibility reports** | Cryptographic signing of eligibility reports (and optionally artifacts) so that provenance is verifiable even when exported. |
| **CI-integrated validation** | Promotion gates and schema/seed checks run in CI; only runs that pass can be linked in eligibility reports, tightening the loop from code change to promotion. |
| **Role-based promotion policies** | Policies that restrict who can promote to accepted (e.g. only “approver” role), or require N approvers, enforced at application or DB layer. |

**Important:** None of these change the core thesis. The current system deliberately avoids hidden cloud state, multi-writer complexity, and API-key dependence. Extensions should preserve **determinism, auditability, and local verifiability**; any that introduce distributed state or multiple sources of truth would need explicit architecture disclosure and migration notes.

---

## 5. Why Local-First Is a Strength

Local-first design is not a limitation—it is what makes the governance guarantees credible.

- **Verifiability** — You can run the same pipeline on the same SQLite file and get the same result. No dependency on a remote service’s view of “current state.” The database is the single source of truth; anyone with the file can verify.
- **No hidden cloud state** — There is no separate control plane, no undocumented API state, no sync layer that might diverge. What you see in the DB is what the system used. Audit and compliance do not rely on trusting a third-party backend.
- **Deterministic builds** — With a fixed DB and deterministic time environment, the same `run_key` and `dataset_id_v2` yield the same `run_instance_id` and reproducible artifacts. Seeds are derived from semantic identity; RC nulls and eligibility results are reproducible. This is only possible when the system does not depend on non-deterministic or opaque cloud services.

By keeping the design single-node and SQLite-first, we keep the **audit trail and promotion logic** in one place, under the user’s control, and fully reproducible. That is the foundation for research governance as infrastructure.

---

## See also

- [Why this system exists](../audit/why_this_system_exists.md) — Failure modes and control surfaces
- [Golden acceptance run](../audit/golden_acceptance_run.md) — Proof of determinism and fail-closed promotion
- [Design](../design.md) — Architecture and data flow
