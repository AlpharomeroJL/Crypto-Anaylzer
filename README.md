# Crypto-Anaylzer — Deterministic Research Validation Control Plane

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-pytest-brightgreen.svg)](#development--verification)

A local-first **research validation control plane** for crypto: it enforces deterministic dataset identity, run identity, fold causality, and fail-closed promotion so that only attested, reproducible results can be promoted. Governance and auditability are enforced at the DB and gatekeeper layers. No API keys, no trading — validation and reports only.

**Who this is for**

- Researchers who need reproducible validation and promotion gates
- Research platform / quant infra engineers who need auditability and determinism

<p align="center">
  <img src="docs/diagrams/architecture_context.svg" alt="System context: Researcher, Crypto-Anaylzer, CEX/DEX APIs, SQLite" width="520"/>
</p>
<p align="center"><sup><a href="docs/diagrams/README.md">All diagrams</a></sup></p>

**What this is (in six bullets):**

- **Validation control plane** — Governs whether a research result is eligible for promotion (candidate/accepted). Does not execute or trade.
- **Content-addressed datasets** — `dataset_id_v2` hashes logical content of allowlisted SQLite tables; one row change changes the id. STRICT mode required for promotion.
- **Deterministic run identity** — `run_key` (semantic) and `run_instance_id` (execution); seeds derived from run_key + salt + version; same config + dataset → same run_key.
- **Fold-causality enforcement** — Purge/embargo in walk-forward splits; train-only fit; attestation artifact required for candidate/accepted when walk-forward is used.
- **Fail-closed promotion** — Candidate and accepted require a passing eligibility report; DB triggers block promotion without it; referenced eligibility reports are immutable.
- **Append-only governance and lineage** — `governance_events`, `artifact_lineage`, and `artifact_edges` are append-only; audit trace from accepted → inputs/configs/artifacts.

---

### Reading paths

| If you want to… | Read this |
|-----------------|-----------|
| **Quickstart (5 minutes)** | [Quickstart](#quickstart) → venv, install, minimal report path. |
| **For researchers** | [Trust model in practice](#trust-model-in-practice), [Key guarantees](#key-guarantees-phase-1-35), [Core workflows](#core-workflows), [Determinism & reproducibility](#determinism--reproducibility). |
| **For engineers** | [Architecture at a glance](#architecture-at-a-glance), [CLI cheatsheet](#cli-cheatsheet), [Development / Verification](#development--verification). |
| **For reviewers** | [Trust model in practice](#trust-model-in-practice), [Promotion model](#promotion-model), [Auditability](#auditability-story), [Methods & limits](docs/methods_and_limits.md), [References](#references). |

---

## Quickstart

Prerequisites: Python 3.10+. No API keys (public endpoints only). Run all commands from the **repo root** after cloning.

### Canonical install (uv)

```powershell

uv venv
uv sync --all-extras
uv run crypto-analyzer --help
uv run crypto-analyzer doctor

```

Minimal path to a research report (after install):

```powershell

uv run crypto-analyzer doctor
uv run crypto-analyzer universe-poll --universe --universe-chain solana --interval 60
uv run crypto-analyzer materialize --freq 1h
uv run crypto-analyzer reportv2 --freq 1h --out-dir reports --hypothesis "baseline momentum"

```

One-command demo: `uv run crypto-analyzer demo`

**Offline path (no network):** Install, then run init, demo-lite, and check-dataset. No config or live data required. CI smoke is for internal stability; demo-lite is for developer onboarding.

```powershell
uv run crypto-analyzer init
uv run crypto-analyzer demo-lite
uv run crypto-analyzer check-dataset --db data/crypto_analyzer.sqlite
```

### Pip fallback

If you prefer pip or uv is not available:

```powershell

python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -U pip setuptools wheel
python -m pip install -e ".[dev]"
python -m crypto_analyzer --help
crypto-analyzer --help

```

Then run commands as `crypto-analyzer <command>` or `python -m crypto_analyzer <command>`.

### Windows: run.ps1 wrapper

On Windows you can use `.\scripts\run.ps1 <command>` as a convenience wrapper. It uses `VIRTUAL_ENV` if set, otherwise `.venv` at repo root, and invokes `python -m crypto_analyzer <command>` (no reliance on PATH). See README Quickstart if the script reports venv not found.

### Troubleshooting

- **`crypto-analyzer` not found** — Use `python -m crypto_analyzer <command>`; it always works when the package is installed.
- **uv sync fails** — Check `uv --version`. Install uv with `python -m pip install -U uv`. Run from repo root.
- **Doctor reports "Not running inside a virtual environment"** — Activate the venv (e.g. `.\.venv\Scripts\activate`) or use `uv run crypto-analyzer doctor` so uv runs inside its environment.
- **run.ps1 fails** — Ensure `.venv` exists at repo root and you are in the repo root when running the script.

### Verification

After install, confirm the CLI works (from repo root):

```powershell

uv run crypto-analyzer doctor

```

Fallback: `python -m crypto_analyzer doctor` (with venv activated).

---

### Trust model in practice

- **Boundaries** — CI enforces import/boundary rules so that execution, broker, and CLI layers cannot be part of the research control plane (core/governance). See [Validation control plane audit](docs/audit/validation_control_plane.md).
- **Reproducibility** — Content-addressed datasets, deterministic run identity, and seeded RNG; promotion requires STRICT dataset hash and provenance. See [Determinism & reproducibility](#determinism--reproducibility) and [Key guarantees](#key-guarantees-phase-1-35) below.
- **Fold causality** — Purge/embargo and train-only fit are enforced; attestation is required for candidate/accepted when walk-forward is used. See [Key guarantees](#key-guarantees-phase-1-35) below and [Methods & Limits](docs/methods_and_limits.md).

### Key guarantees (Phase 1–3.5)

- **dataset_id_v2** — Content-addressed hashing of allowlisted tables (canonical ordering); STRICT for promotion.
- **run_key + run_instance_id** — Semantic run identity and execution instance; run_key excludes timestamps/paths.
- **Deterministic RNG** — `seed_root(run_key, salt, version)`; salted, reproducible across processes; `seed_version` in artifacts.
- **Calibration harness** — BH/BY, RC, RW, CSCV PBO, bootstrap, HAC: CI-safe Type I (and FDR/RC/RW) checks; guards, not full statistical certification.
- **Fold-causality + attestation** — Purge/embargo, train-only fit; attestation artifact with schema version; gatekeeper requires valid attestation when walk-forward used.
- **Fail-closed promotion** — Eligibility reports + DB triggers; no candidate/accepted without linked passing report at same level; evidence immutable when referenced.
- **Append-only governance_events** — All evaluate/promote actions logged; no updates or deletes.
- **artifact_lineage + artifact_edges** — Audit graph from accepted → run → configs/versions/artifacts.
- **SQLite authoritative** — Single source of truth for governance and lineage; optional DuckDB analytics backend (read-only for governance).

### System guarantees

| Risk | Control | Enforcement mechanism | Verified by |
|------|---------|------------------------|-------------|
| Data drift | dataset_id_v2 | Content-addressed hash + STRICT requirement for promotion | test_dataset_v2.py |
| Seed drift | seed_root + versioned salts | SEED_ROOT_VERSION; deterministic RNG across processes | Deterministic tests (e.g. test_reportv2_deterministic_rerun, test_statistics_research) |
| Promotion bypass | DB triggers | candidate/accepted require linked passing eligibility_report_id; trigger blocks UPDATE/DELETE without it | test_migrations_phase3.py |
| Leakage (fold) | fold_causality_attestation | Purge/embargo, train-only fit; gatekeeper requires valid attestation when walk-forward used | test_fold_causality_attestation.py, test_promotion_requires_fold_causality_attestation.py, test_transform_fit_called_only_on_train.py |
| RC provenance ambiguity | rc_summary schema version + seed_root | rc_summary_schema_version; seed_root/component_salt in RC summary; gatekeeper version check | test_calibration_rc_smoke.py, test_promotion_gating.py |
| Artifact mutability | sha256 + artifact_lineage | compute_file_sha256; artifact_lineage rows with sha256; append-only lineage triggers | test_artifact_lineage_*.py, test_lineage_reproducibility_same_run_key_same_hashes.py |

### Design rationale

**Why deterministic IDs?** So every run is traceable and repeatable: same inputs and config produce the same `dataset_id_v2`, `run_key`, and artifact hashes. That lets you compare runs, invalidate caches when data changes, and prove reproducibility in audits. **Why opt-in migrations?** Phase 3 (regimes, promotion, lineage) adds schema and behavior that not every user needs. **Why governance modeling?** Research that moves toward production needs a path from “exploratory” to “accepted” with clear gates (eligibility reports, fold attestation, RC/RW when enabled) and an append-only audit log.

### Auditability and proof bundle

If you only read one thing: run the [Golden acceptance run](docs/audit/golden_acceptance_run.md) and inspect the DB-only audit trace.

- **[Golden acceptance run](docs/audit/golden_acceptance_run.md)** — Copy-paste PowerShell steps for a minimal and full proof: deterministic run, promotion to accepted, trigger check, and DB-only audit trace. One-command-ish proof of accepted promotion and provenance.
- **[Methods & implementation alignment](docs/audit/methods_implementation_alignment.md)** — Mapping from method (dataset_id_v2, RC/RW, seed_root, schema versions, etc.) to code and artifact keys.

---

## Research rigor & overfitting defenses

Signal discovery is treated as a **multiple-testing problem under dependence**. Key controls: walk-forward (purge/embargo, train-only fit, fold-causality attestation); deflated Sharpe with Neff; PBO-style/CSCV; BH/BY; optional Reality Check and Romano–Wolf; HAC mean inference. **Details:** [Methods & Limits](docs/methods_and_limits.md), [Statistical Methods Appendix](docs/appendix/statistical_methods.md), [implementation-aligned formulae](docs/appendix/methods_limits_implementation.md).

---

## Architecture at a glance

<p align="center">
  <img src="docs/diagrams/architecture_internal.svg" alt="Internal architecture: four stages, one SQLite database" width="640"/>
</p>

```mermaid
flowchart TB
    subgraph Data["Data layer"]
        SQLiteInputs[("SQLite research tables\n(bars_*, snapshots, universe)")]
        DatasetHash["dataset_id_v2\ncontent-addressed hash\n(STRICT/FAST_DEV)"]
        SQLiteInputs --> DatasetHash
    end

    subgraph RunIdentity["Run identity"]
        RunKey["run_key\n(semantic)"]
        RunInstanceId["run_instance_id\n(execution)"]
        RunContext["RunContext\n(seed_version, versions)"]
        RunKey --> RunContext
        RunInstanceId --> RunContext
        DatasetHash --> RunKey
    end

    subgraph Eval["Evaluation"]
        FoldSplits["Fold splits\n(purge/embargo)"]
        Scoring["Scoring / metrics"]
        FoldSplits --> Scoring
    end

    subgraph Validation["Validation"]
        BHBY["BH/BY, RC, RW\nCSCV PBO, HAC"]
        CalHarness["Calibration harness"]
        BHBY --> CalHarness
    end

    subgraph Artifacts["Artifacts"]
        ValBundle["validation_bundle\nfold_causality_attestation\nrc_summary"]
    end

    subgraph Governance["Governance"]
        EvalElig["evaluate_eligibility\n→ eligibility_reports"]
        PromCand["promotion_candidates\n(exploratory→candidate→accepted)"]
        DBTriggers["DB triggers\nfail-closed"]
        GovEvents["governance_events\n(append-only)"]
        EvalElig --> PromCand
        PromCand --> DBTriggers
        EvalElig --> GovEvents
        PromCand --> GovEvents
    end

    subgraph Lineage["Lineage"]
        ArtLineage["artifact_lineage\nartifact_edges"]
    end

    RunContext --> Eval
    Eval --> Validation
    Validation --> Artifacts
    Artifacts --> EvalElig
    Artifacts --> ArtLineage
    Governance --> Lineage
```

Full diagram source: [docs/architecture/validation_control_plane.mmd](docs/architecture/validation_control_plane.mmd).

---

## Core workflows

1. **Ingest** — Poll writes to `spot_price_snapshots`, `sol_monitor_snapshots`, universe tables. `run_migrations` applies core + v2 factor tables.
2. **Bars** — Raw snapshots → deterministic OHLCV bars (5min, 15min, 1h, 1D). Idempotent.
3. **Factors** — Rolling OLS (or optional Kalman) vs BTC/ETH → residual returns. Materialized to `factor_model_runs`, `factor_betas`, `residual_returns`; identified by `dataset_id` and `factor_run_id`.
4. **Signals** — Cross-sectional factors; winsorized z-scores; signal panels.
5. **Validation** — IC, IC decay; per-signal ValidationBundle (paths, metrics). Fold causality: purge/embargo, attestation when walk-forward used.
6. **Corrections** — Deflated Sharpe, PBO proxy, block bootstrap, BH/BY; optional Reality Check (reportv2 `--reality-check`, `family_id`).
7. **Reporting** — reportv2; optional regime-conditioned IC with `--regimes REGIME_RUN_ID`; Streamlit dashboard; experiment registry; manifests. **Promotion** — Create candidate; evaluate eligibility; promote to candidate/accepted via governance entrypoint; all actions logged to `governance_events`.

---

## CLI cheatsheet

Run any command as **`crypto-analyzer <command> [args...]`** or **`python -m crypto_analyzer <command> [args...]`** (cross-platform). On Windows, **`.\scripts\run.ps1 <command> [args...]`** is a convenience wrapper that invokes the same CLI.

| Command | Description |
|---------|-------------|
| `doctor` | Preflight: environment, DB schema, pipeline smoke test |
| `doctor --ci` | CI-safe preflight (no network, temp DB, migrations + tables) |
| `smoke --ci` | Synthetic-data, no-network smoke (migrations, dataset_id_v2, run identity) |
| `init` | Create local SQLite DB and run migrations (default `data/crypto_analyzer.sqlite`; optional `--phase3`) |
| `demo-lite` | Synthetic dataset, no network; run after init for offline onboarding |
| `poll` | Single-pair data poll (provider fallback) |
| `universe-poll --universe ...` | Multi-asset universe discovery (e.g. `--universe-chain solana`) |
| `materialize` | Build OHLCV bars (e.g. `--freq 1h`) |
| `reportv2` | Research report: IC, PBO, QP; optional `--regimes`, `--reality-check`, `--execution-evidence` when Phase 3 enabled |
| `walkforward` | Walk-forward backtest, out-of-sample fold stitching |
| `promotion` | Promotion subcommands: list, create, evaluate |
| `verify` | Full gate: doctor → pytest → ruff → research-only boundary → diagram export |
| `test` | Run pytest |
| `streamlit` | Interactive dashboard |
| `demo` | One-command demo: doctor → poll → materialize → report |
| `check-dataset` | Inspect dataset fingerprints and row counts |

---

## Promotion model

- **exploratory** — No gate; warnings only.
- **candidate** — Requires passing `evaluate_eligibility(..., level="candidate")`: STRICT dataset_id_v2, run_key, engine_version, config_version, seed_version; fold attestation when walk-forward used; RC/RW contract when enabled. Result stored in `eligibility_reports`; DB trigger blocks status without linked passing report.
- **accepted** — Same fail-closed requirement at level `accepted`; eligibility_report_id and report level must match status.

Walk-forward runs require a valid fold-causality attestation (schema version, purge_applied, embargo_applied, train_only_fit_enforced) for candidate/accepted.

Promotion gating is policy-only and does not perform I/O; filesystem and evidence loading live in the service and execution_evidence layer.

---

## Auditability story

How to trace an accepted result (without reading report files):

1. **promotion_candidates** — Filter `status = 'accepted'`; get `candidate_id`, `eligibility_report_id`.
2. **eligibility_reports** — Join on `eligibility_report_id`; get `run_key`, `run_instance_id`, `dataset_id_v2`, `passed`, `level`, `blockers_json`, `computed_at_utc`.
3. **governance_events** — Filter by `candidate_id`; order by `event_id`; see sequence of evaluate/promote and actors.
4. **artifact_lineage** — Filter by `run_key` or `run_instance_id`; get `artifact_id`, `artifact_type`, `sha256`, `created_utc` for that run.
5. **artifact_edges** — Join on `child_artifact_id` / `parent_artifact_id` to walk graph (e.g. validation_bundle → fold_causality_attestation, rc_summary).
6. **Versions** — From eligibility report or artifact_lineage: `engine_version`, `config_version`, `dataset_id_v2`; from bundle meta or attestation: `seed_version`, schema versions.

---

## Determinism & reproducibility

| ID or mechanism | What it keys |
|-----------------|--------------|
| **dataset_id_v2** | Content-addressed hash of allowlisted tables (logical content, canonical ordering). STRICT for promotion. |
| **run_key** | Deterministic hash of semantic payload (dataset_id_v2, config, versions); excludes timestamps/paths. |
| **run_instance_id** | Execution instance (e.g. manifest run_id); same run_key can have many instances. |
| **factor_run_id** | Hash of dataset_id + factor config (freq, window, estimator). |
| **family_id** | Reality Check family (signal×horizon); used in RC cache and promotion gating. |
| **Artifact SHA256** | File hashes for validation bundles and outputs; deterministic rerun test compares bundle and manifest bytes. |
| **CRYPTO_ANALYZER_DETERMINISTIC_TIME** | Fixes timestamps so materialize and reportv2 produce identical outputs on rerun. Intended for deterministic rerun testing; does not change promotion eligibility gates (STRICT dataset hash and provenance still required). |
| **Bootstrap / RC seed** | Derived via `seed_root(run_key, salt, version)`; seed_version in artifacts; reproducible null distributions and CIs. |

---

## Development / Verification

Exact commands (PowerShell). Run from repo root with venv activated (e.g. `.venv\Scripts\activate`).

**Doctor:** `crypto-analyzer doctor` = full local preflight (env, DB, pipeline). `crypto-analyzer doctor --ci` = CI-safe: no network, temp DB only; validates migrations and expected tables (core ingestion, phase3 promotion/governance, lineage).

**CI smoke (no network):**

```powershell
crypto-analyzer smoke --ci
```

**Architecture refactor plan (no behavior change):** Package boundaries and compatibility shims are documented in [Refactor move map](docs/audit/refactor_move_map.md). That doc describes the target layout (core, data, artifacts, stats, pipeline, governance, execution, compute), shims (e.g. `crypto_analyzer.rng` → `core.seeding`), and verification commands. **Public API contract / refactor policy:** [public_api_contract.md](docs/audit/public_api_contract.md) defines stable facades, compatibility shims policy, import boundaries, and how to add new exports. The public API surface is frozen for release; see the contract doc for the exact `__all__` and versioning.

### Tier 1: Fast checks

```powershell
python -m ruff check .
python -m ruff format .
python -m pytest -m "not slow" -q --tb=short
```

- **ruff:** All checks passed.
- **pytest -m "not slow":** Skips tests marked `@pytest.mark.slow` (full report pipeline). Typical runtime under a few minutes. See `pyproject.toml` for the `slow` marker.

**Pre-release checklist (venv only, no uv):** If `uv` is not in PATH, run from repo root with venv activated (e.g. `.\.venv\Scripts\activate`). Use these in order:

```powershell
python -m ruff check .
python -m ruff format --check .
python tools/check_version_changelog.py --expected-version 0.3.0
python -m crypto_analyzer --help
crypto-analyzer --help
crypto-analyzer doctor --ci
$env:CRYPTO_ANALYZER_NO_NETWORK="1"; crypto-analyzer smoke --ci
python -m pytest -m "not slow" -q --tb=short
```

(Skip `uv lock --check` if uv is not installed; CI runs it.)

### Tier 2: Phase-specific targeted suites

Tier 2 lists common debug targets. The canonical gate is Tier 1 + `.\scripts\run.ps1 verify`. If filenames change, use `ls tests/test_*` (or equivalent) to locate the current modules.

**Dataset v2 and run identity:**

```powershell
python -m pytest tests/test_dataset_v2.py tests/test_run_identity.py tests/test_backfill_dataset_v2.py -v --tb=short
```

**RNG and bootstrap:**

```powershell
python -m pytest tests/test_statistics_research.py -v --tb=short
```

**Calibration (BH/BY, RC, RW, CSCV, Type I) — smoke:**

```powershell
python -m pytest tests/test_calibration_fdr_smoke.py tests/test_calibration_cscv_smoke.py tests/test_calibration_rc_smoke.py tests/test_calibration_rw_smoke.py tests/test_calibration_harness_type1.py -v --tb=short
```

**Fold causality and attestation:**

```powershell
python -m pytest tests/test_fold_causality_attestation.py tests/test_promotion_requires_fold_causality_attestation.py tests/test_transform_fit_called_only_on_train.py -v --tb=short
```

**Promotion gating and eligibility:**

```powershell
python -m pytest tests/test_promotion_gating.py tests/test_gatekeeper_requires_versions_and_seed_version.py tests/test_promotion_service.py tests/test_audit_invariants_fail_closed.py -v --tb=short
```

**Phase 3 migrations and governance:**

```powershell
python -m pytest tests/test_migrations_phase3.py tests/test_governance_event_log_append_only.py tests/test_artifact_lineage_append_only.py tests/test_artifact_lineage_written.py tests/test_acceptance_audit_trace.py -v --tb=short
```

**Determinism and Reality Check:**

```powershell
python -m pytest tests/test_reportv2_deterministic_rerun.py tests/test_research_pipeline_smoke.py tests/test_reality_check_null_sanity.py -v --tb=short
```

*(Optional: DuckDB backend tests require DuckDB; skip if not installed.)*

### Tier 3: Full test suite

```powershell
python -m pytest -q --tb=short
```

**Full verification script** (doctor → pytest → ruff → research-only boundary → diagram export):

```powershell
.\scripts\run.ps1 verify
```

### Docs formatting

Some docs include Mermaid diagrams and math. To normalize for GitHub (fenced Mermaid, `$...$` / `$$...$$` math):

```powershell
python scripts/normalize_markdown_math.py
```

To check only: `python scripts/normalize_markdown_math.py --check`

### Security

- **Vulnerability scanning:** CI runs `pip-audit` (weekly schedule and on push to main). The job requires network for advisories and is separate from smoke/demo-lite so those remain guaranteed offline.
- **SBOM:** CycloneDX SBOM is generated and uploaded as a workflow artifact (`sbom-cyclonedx`).
- **Offline guarantees:** `smoke --ci` and `demo-lite` (with `CRYPTO_ANALYZER_NO_NETWORK=1`) are enforced network-free in CI. See [SECURITY.md](SECURITY.md) for supported versions and reporting.

---

## References

Canonical references for the statistical and econometric methods used in the validation stack:

- **Deflated Sharpe Ratio (DSR) / effective trials (Neff):** Bailey, D., & López de Prado, M. (2014). The Deflated Sharpe Ratio. *Journal of Portfolio Management*, 40(5), 94–107.
- **Benjamini–Hochberg (BH):** Benjamini, Y., & Hochberg, Y. (1995). Controlling the False Discovery Rate: A Practical and Powerful Approach to Multiple Testing. *Journal of the Royal Statistical Society B*, 57(1), 289–300.
- **Benjamini–Yekutieli (BY):** Benjamini, Y., & Yekutieli, D. (2001). The Control of the False Discovery Rate in Multiple Testing Under Dependency. *Annals of Statistics*, 29(4), 1165–1188.
- **White's Reality Check:** White, H. (2000). A Reality Check for Data Snooping. *Econometrica*, 68(5), 1097–1126.
- **Romano–Wolf stepdown:** Romano, J. P., & Wolf, M. (2005). Stepwise Multiple Testing as Formalized Data Snooping. *Econometrica*, 73(4), 1237–1282.
- **CSCV / PBO (Bailey et al.):** Bailey, D. H., Borwein, J., López de Prado, M., & Zhu, Q. J. (2014). Pseudo-Mathematics and Financial Charlatanism: The Effects of Backtest Overfitting on Out-of-Sample Performance. *Notices of the AMS*, 61(5), 458–471.
- **Stationary bootstrap (Politis & Romano):** Politis, D. N., & Romano, J. P. (1994). The Stationary Bootstrap. *Journal of the American Statistical Association*, 89(428), 1303–1313.
- **Newey–West / HAC:** Newey, W. K., & West, K. D. (1987). A Simple, Positive Semi-Definite, Heteroskedasticity and Autocorrelation Consistent Covariance Matrix. *Econometrica*, 55(3), 703–708.

Short form and artifact keys: [Methods & limits](docs/methods_and_limits.md) (§19). Formal definitions: [Statistical Methods Appendix](docs/appendix/statistical_methods.md). Repo formulae: [implementation-aligned](docs/appendix/methods_limits_implementation.md).

---

## Limitations

- **Single-node, local-first** — Not distributed; one SQLite DB per environment.
- **Not a multi-user concurrent platform** — No built-in concurrency control for concurrent promotion or lineage writes.
- **Research validation only** — No execution, order routing, or live trading.
- **Calibration harness** — CI-safe guards (Type I, FDR, RC, RW, CSCV, bootstrap); not full statistical certification under all data-generating processes.
- **Scalability** — SQLite is the single store; suitable for research and moderate history. Optional DuckDB for read-heavy analytics; governance and lineage remain in SQLite.
- **Data scope:** Ingestion is public CEX/DEX only; no authenticated feeds. No real-time execution or order routing.

---

## Repository map

| Directory / module | Purpose |
|--------------------|---------|
| **crypto_analyzer/core/** | RunContext, run identity (`run_identity.py`), context |
| **crypto_analyzer/dataset_v2.py** | dataset_id_v2 hashing, backfill |
| **crypto_analyzer/fold_causality/** | Folds, purge/embargo, attestation, runner |
| **crypto_analyzer/governance/** | promote, audit, audit_invariants |
| **crypto_analyzer/promotion/** | gating (evaluate_eligibility), service, store_sqlite |
| **crypto_analyzer/db/** | migrations_phase3, lineage, governance_events |
| **crypto_analyzer/store/** | sqlite_backend, duckdb_backend (lineage → SQLite) |
| **crypto_analyzer/rng.py** | seed_root, salts, SEED_ROOT_VERSION |
| **crypto_analyzer/stats/** | reality_check, calibration_*, multiple_testing |
| **crypto_analyzer/contracts/** | validation_bundle_contract, schema_versions |
| **cli/** | research_report_v2, poll, materialize, promotion |
| **tests/** | test_dataset_v2, test_run_identity, test_promotion_*, test_artifact_lineage_*, etc. |
| **docs/audit/** | validation_control_plane.md, phase1_verification.md |
| **docs/architecture/** | validation_control_plane.mmd |
| **docs/spec/** | system_overview, stats_stack_upgrade_acceptance |
| **scripts/** | run.ps1, export_diagrams.ps1 |

---

## Documentation index

| Document | Contents |
|----------|----------|
| [Methods & limits](docs/methods_and_limits.md) | Statistical methods, assumptions, artifact keys, limitations (DSR, PBO, BH/BY, RC, RW, HAC, breaks, capacity). See: [Statistical Methods Appendix](docs/appendix/statistical_methods.md). |
| [Stats stack acceptance](docs/spec/stats_stack_upgrade_acceptance.md) | Definition of done for upgrades #1–#6; exact artifact keys; minimum data thresholds; golden run command. |
| [Statistical Methods Appendix](docs/appendix/statistical_methods.md) | Formal definitions, assumptions, derivations/proof sketches for DSR, PBO, BH/BY, bootstrap, Reality Check, HAC (Appendices A & B). |
| [Methods & Limits — implementation-aligned](docs/appendix/methods_limits_implementation.md) | Exact repo formulae: DSR, Neff, PBO proxy + CSCV PBO, BH/BY, bootstrap, RC, Romano–Wolf, HAC, break diagnostics, capacity curve. |
| [Validation control plane audit](docs/audit/validation_control_plane.md) | Threat model, design, governance, reproducibility, gaps. |
| [Phase 3 summary](docs/phase3_summary.md) | Phase 3 migrations, governance, lineage, store. |
| [Phase 1 verification](docs/audit/phase1_verification.md) | Phase 1 verification checklist (dataset_id_v2, run_key, backfill). |
| [Research validation workflow](docs/research_validation_workflow.md) | Exploratory vs full-scale runs, run_id, snapshot semantics, validation readiness criteria. |
| [Spec index (canonical)](docs/spec/README.md) | Master spec, system overview, implementation ledger, component specs. |
| [System overview](docs/spec/system_overview.md) | Pipeline lifecycle, determinism, statistical stack, feature flags, promotion. |
| [Implementation ledger](docs/spec/implementation_ledger.md) | Requirement → status, PRs, evidence. |
| [Design](docs/design.md) | Data flow, provider contracts, failure modes. |
| [Architecture](docs/architecture.md) | Module responsibility matrix. |
| [Contributing](CONTRIBUTING.md) | Dev setup, testing, style, adding providers, verify. |
| [Diagrams](docs/diagrams/README.md) | PlantUML index and export. |
| [Audit notes](docs/audit/README.md) | Architecture audits and alignment reports. |

---

## Release / Verification status

- [Validation control plane audit](docs/audit/validation_control_plane.md)
- [Phase 3 summary](docs/phase3_summary.md)
- [Phase 1 verification](docs/audit/phase1_verification.md)

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No data in dashboard | Run `poll` (or universe-poll) then `materialize`. |
| Bars table not found | Run `.\scripts\run.ps1 materialize --freq 1h`. |
| Provider DOWN | Circuit breaker; auto-recovers after cooldown. |
| reportv2 --regimes fails | Set `CRYPTO_ANALYZER_ENABLE_REGIMES=1`, run Phase 3 migrations, then regime materialize. |
| Verify fails | Run `doctor`; ensure venv active; fix ruff/pytest as indicated. |

---

## License and disclaimer

MIT License. See [LICENSE](LICENSE).

**Research-only.** This tool analyzes data and produces reports. It does not execute trades, hold API keys, or connect to any broker. Opt-in features (regimes, Phase 3 migrations, Reality Check, promotion) do not change default behavior.
