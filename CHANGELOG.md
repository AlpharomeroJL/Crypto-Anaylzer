# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Releases must use a header `## [X.Y.Z] - YYYY-MM-DD` (or `## [vX.Y.Z]`). The first such line is the latest release and must match `crypto_analyzer.__version__`. See `tools/check_version_changelog.py`.

---

## [0.3.0] - 2026-02-23

### Release pipeline and dev UX

- Version/changelog consistency check (`tools/check_version_changelog.py`).
- Release workflow: build sdist/wheel on tag push; optional PyPI publish.
- `crypto-analyzer init`: create local SQLite DB and run migrations (optional `--phase3`).
- `crypto-analyzer demo-lite`: synthetic dataset, no network, for offline onboarding.
- Security: dependency audit and SBOM in CI; SECURITY.md and README Security section.

---

## [v0.1.0] — Deterministic Research Validation Control Plane

Initial release of the validation control plane: deterministic identity, statistical defenses, governance, lineage, and proof artifacts for auditable research and fail-closed promotion.

### Phase 1 — Dataset identity + run identity

- **dataset_id_v2** — Content-addressed dataset identity. Same DB content yields the same id; promotion requires STRICT mode.
- **run_key** — Semantic run identity (hash of dataset_id_v2, config, engine_version, config_version); excludes timestamps and paths.
- **run_instance_id** — Execution instance identifier; separates semantic identity from a single run execution.
- Deterministic run identity under `CRYPTO_ANALYZER_DETERMINISTIC_TIME=1`.

### Phase 2 — Statistical stack + calibration

- **Multiple testing** — BH/BY FDR, deflated Sharpe (DSR), effective trials (Neff).
- **Reality Check** — White-style RC with seeded nulls; optional Romano–Wolf stepdown.
- **CSCV PBO** — Probability of backtest overfitting (with documented split-sampling deviation).
- **HAC** — Newey–West long-run variance for mean inference.
- **Calibration harness** — Type I / FDR calibration experiments with deterministic RNG when run_key is set.
- **seed_root** — Central RNG root from run_key, salt, version (optional fold_id); RC and artifacts carry seed provenance.

### Phase 3 — Governance + lineage

- **eligibility_reports** — Pass/fail evaluation per level (exploratory, candidate, accepted); provenance (run_key, dataset_id_v2, engine/config versions).
- **Promotion states** — exploratory → candidate → accepted; transitions require a passing eligibility report; DB triggers block direct UPDATE without a valid eligibility_report_id (fail-closed).
- **governance_events** — Append-only log of promotion actions (actor, candidate_id, eligibility_report_id, run_key, dataset_id_v2); UPDATE/DELETE blocked by triggers.
- **artifact_lineage** — Append-only record of artifact_id, run_instance_id, run_key, dataset_id_v2, hashes, schema versions.
- **artifact_edges** — Parent/child relations between artifacts.
- Fold-causality attestation for walk-forward; promotion can require attestation and RC summary.

### Phase 3.5 — Core canonicalization + proof bundle

- Schema versions in code and artifacts; gatekeeper requires exact version match for promotion.
- Validation bundle and proof bundle canonicalization; evidence and provenance in promotion flow.
- RC summary and execution evidence paths wired into promotion create/evaluate CLI.

### Proof artifact

- Documented control plane: [Validation Control Plane Whitepaper](docs/audit/validation_control_plane_whitepaper.md).
- Institutional failure modes and controls: [Why This System Exists](docs/audit/why_this_system_exists.md).
- Methods implementation alignment and known deviations documented for auditors.

### Golden Acceptance Run

- Copy-paste procedure in [Golden acceptance run — proof bundle](docs/audit/golden_acceptance_run.md).
- Demonstrates: deterministic dataset and run identity, seeded RNG provenance, fail-closed promotion, trigger enforcement, append-only governance and lineage, DB-only audit trace from acceptance back to eligibility and artifact lineage.
- Determinism tests: `test_reportv2_deterministic_rerun`, `test_reality_check_deterministic`, `test_reality_check_rng_determinism`; acceptance audit trace tests.

---

[v0.1.0]: https://github.com/jo312/Crypto-Anaylzer/releases/tag/v0.1.0
