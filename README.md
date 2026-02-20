# Crypto-Analyzer  
## Deterministic Crypto Research Platform

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-pytest-brightgreen.svg)](#verification)

Crypto-Analyzer is a **deterministic, research-grade** crypto alpha platform with:

- **Provider-agnostic ingestion** — pluggable CEX/DEX sources, retry/backoff, circuit breakers, last-known-good cache
- **Versioned schema migrations** — core + v2 factor tables; Phase 3 (regimes, promotion) opt-in only
- **Factor and regime modeling** — rolling OLS (or optional Kalman beta), residual returns, optional regime detection
- **Data-snooping corrections** — Reality Check (max-statistic bootstrap), null model validation suite
- **Promotion workflow with audit trail** — exploratory → candidate → accepted; ValidationBundle, optional regime robustness and Reality Check gates
- **Single SQLite source of truth** — no API keys, no cloud; all analytics and experiment state in one DB

This is a **research system** with governance and statistical rigor, not a toy dashboard. It does not execute trades or hold broker credentials.

---

## Architecture Overview

```
  Providers (CEX/DEX) → Ingest (migrations, chains) → SQLite
       → Materialize (bars, factors, regimes opt-in)
       → Research Pipeline (signals, IC, QP, walk-forward)
       → Validation → Statistical corrections → Promotion (opt-in)
       → Reporting / UI (Streamlit, FastAPI read-only, CLI)
```

- **Ingest / read_api boundary:** Poll uses `crypto_analyzer.ingest` (DB writes, migrations, provider chains). Dashboard and health use `read_api` only; no direct DB imports in CLI/UI.
- **Single source of truth:** All analytics consume the same SQLite database. Bar and factor materialization are deterministic and idempotent.
- **Versioned migrations:** `run_migrations` applies core + v2 (factor tables). Phase 3 (regime_runs, regime_states, promotion_candidates, promotion_events, sweep tables) only when regimes are enabled; see [Data Model & Migrations](#data-model--migrations).

For full pipeline and contracts, see [docs/spec/system_overview.md](docs/spec/system_overview.md).

---

## Data Model & Migrations

- **run_migrations** — Core tables (snapshots, bars, provider_health, universe) and v2 factor tables (`factor_model_runs`, `factor_betas`, `residual_returns`). Applied when opening the DB via ingest.
- **run_migrations_phase3** — Regime and promotion tables (`regime_runs`, `regime_states`, `promotion_candidates`, `promotion_events`, `sweep_families`, `sweep_hypotheses`). Opt-in; not run by default. Requires `CRYPTO_ANALYZER_ENABLE_REGIMES=1` (or explicit Phase 3 migration call) for regime/promotion features.
- **Versioned schema** — Migrations are idempotent (CREATE TABLE IF NOT EXISTS, etc.). Single SQLite file holds all ingested data, bars, factor runs, and (when opted in) regime and promotion state.

---

## Research Pipeline

1. **Factor decomposition** — Rolling OLS (or optional Kalman) vs BTC/ETH → idiosyncratic residuals; dataset_id and factor_run_id identify runs.
2. **Signals** — Cross-sectional factors (size, volume, momentum); winsorized z-scores; signal panels.
3. **Validation** — IC, IC decay, orthogonalization; per-signal ValidationBundle (paths, metrics).
4. **Portfolio** — Constrained QP (scipy SLSQP), volatility targeting, beta neutralization, execution cost model (fees + slippage).
5. **Walk-forward backtest** — Strict train/test separation, no lookahead; stitched OOS results.

**Optional (opt-in):**

- **Regime models** — Legacy classify or Phase 3 RegimeDetector (fit/predict); reportv2 `--regimes REGIME_RUN_ID` for regime-conditioned IC.
- **Reality Check** — reportv2 `--reality-check`; family_id; bootstrap null for data snooping; RC cache by family_id + config + dataset + git.
- **Promotion workflow** — Create candidate from run/bundle; evaluate (IC, t-stat, BH-adjusted p-value, optional regime robustness, RC, execution evidence); promotion_events audit log.

---

## Statistical Defense Stack

- Walk-forward splits (strict temporal separation)
- Block bootstrap (seeded; serial correlation preserved)
- Deflated Sharpe ratio
- PBO proxy (probability of backtest overfitting)
- Multiple-testing correction (BH/BY; adjusted p-values in registry)
- Reality Check (max-statistic bootstrap; opt-in; family_id)
- Romano–Wolf stub (feature-flagged; currently NotImplementedError)

---

## Determinism & Reproducibility

| Mechanism | Role |
|-----------|------|
| **dataset_id** | Stable hash from table summaries (row counts, min/max ts). Dataset change invalidates derived caches. |
| **factor_run_id** | Hash of dataset_id + factor config (freq, window, estimator). Identifies one factor materialization run. |
| **regime_run_id** | Identifies one regime materialization run (when regimes enabled). |
| **family_id** | Stable id for Reality Check family (signal×horizon family); used in RC cache and promotion gating. |
| **Artifact SHA256** | File hashes for validation bundles and outputs; deterministic rerun test compares bundle and manifest bytes. |
| **CRYPTO_ANALYZER_DETERMINISTIC_TIME** | Fixed timestamps so materialize and reportv2 produce identical outputs on rerun. |
| **Bootstrap / RC seed** | Fixed seed in config → reproducible null distributions and CIs; seed stored in artifacts. |
| **verify** | Single command runs doctor, pytest (no network), ruff, research-only boundary check, diagram export. |

No test performs live HTTP. All research tests are deterministic where applicable.

---

## Research Governance and Promotion

- **States:** Exploratory → Candidate → Accepted. Stored in `promotion_candidates` and `promotion_events` (Phase 3 tables).
- **Backed by:** ValidationBundle (per-signal paths and metrics); optional regime robustness; optional Reality Check (enforced for accept when candidate belongs to a sweep family unless override); optional execution evidence for capacity/execution realism.
- **Promotion events** — Append-only audit log: status changes, thresholds_used, warnings; evidence_json stores paths (validation_bundle_path, execution_evidence_path) for traceability.

CLI: `promotion list`, `promotion create`, `promotion evaluate`. Streamlit: Promotion page. See [docs/spec/phase3_promotion_slice5_alignment.md](docs/spec/phase3_promotion_slice5_alignment.md) and [docs/spec/system_overview.md](docs/spec/system_overview.md).

---

## Getting Started

**Prerequisites:** Python 3.10+. No API keys (public endpoints only).

```powershell
git clone https://github.com/AlpharomeroJL/Crypto-Anaylzer.git && cd Crypto-Anaylzer
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Quick demo:** `.\scripts\run.ps1 demo`

**Step-by-step:**

```powershell
.\scripts\run.ps1 doctor
.\scripts\run.ps1 universe-poll --universe --universe-chain solana --interval 60
.\scripts\run.ps1 materialize --freq 1h
.\scripts\run.ps1 reportv2 --freq 1h --out-dir reports --hypothesis "baseline momentum"
.\scripts\run.ps1 streamlit
```

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `doctor` | Preflight: environment, dependencies, DB schema, pipeline smoke test |
| `poll` | Single-pair data poll (provider fallback) |
| `universe-poll --universe ...` | Multi-asset universe discovery with churn controls |
| `materialize` | Build deterministic OHLCV bars (5min, 15min, 1h, 1D) |
| `analyze` | Legacy single-pair analysis (momentum, vol) |
| `scan` | Multi-mode scanner (momentum, residual, vol breakout, mean reversion) |
| `report` | Research report (v1, single-factor) |
| `reportv2` | Research report with IC, orthogonalization, PBO, QP, experiment logging; optional `--regimes`, `--reality-check`, `--execution-evidence` when Phase 3 enabled |
| `daily` | Daily market structure report |
| `backtest` | Single-asset backtest (trend following, volatility breakout) |
| `walkforward` | Walk-forward backtest with out-of-sample fold stitching |
| `streamlit` | Interactive dashboard (12 pages) |
| `api` | Local read-only research API (FastAPI) |
| `demo` | One-command demo: doctor → poll → materialize → report |
| `null_suite` | Null/placebo artifact runner (random ranks, permuted signal, block shuffle) |
| `verify` | Full gate: doctor → pytest → ruff → research-only boundary → diagrams |
| `test` | Run pytest |
| `check-dataset` | Inspect dataset fingerprints and row counts |
| `promotion` | Promotion subcommands: list, create, evaluate |

All commands: `.\scripts\run.ps1 <command> [args...]`

---

## Verification

`.\scripts\run.ps1 verify` runs:

1. **doctor** — Environment, DB, pipeline smoke
2. **pytest** — Full test suite (no network; all HTTP mocked)
3. **ruff** — Lint
4. **research-only boundary** — Forbidden keywords (no order/submit/broker/api_key/secret etc.)
5. **diagram export** — Required PlantUML sources present and export to SVG

No test performs live HTTP. All research tests are deterministic where applicable. Fix lint with `ruff check .` and `ruff format .`. Diagram export: `.\scripts\export_diagrams.ps1` (see [docs/diagrams/README.md](docs/diagrams/README.md)).

---

## Extension

Add a new spot provider by implementing `SpotPriceProvider`: `provider_name`, `get_spot(symbol)` returning `SpotQuote`. Register in `crypto_analyzer/providers/defaults.py` and add to `config.yaml` under `providers.spot_priority`. For DEX: implement `DexSnapshotProvider` (`get_snapshot(chain_id, pair_address)`, `search_pairs(query, chain_id)`); see `crypto_analyzer/providers/dex/dexscreener.py`. The provider chain handles retry, circuit breaker, and last-known-good cache.

---

## Documentation Index

| Document | Contents |
|----------|----------|
| [System overview](docs/spec/system_overview.md) | Pipeline lifecycle, determinism, statistical stack, promotion summary |
| [Implementation ledger](docs/spec/implementation_ledger.md) | Spec requirements, phase status, evidence |
| [Design](docs/design.md) | Data flow, provider contracts, failure modes |
| [Architecture](docs/architecture.md) | Module responsibility matrix |
| [Contributing](CONTRIBUTING.md) | Dev setup, testing, style, adding providers, verify |
| [Diagrams](docs/diagrams/README.md) | PlantUML index and export |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No data in dashboard | Run `poll` (or universe-poll) then `materialize` |
| Bars table not found | Run `.\scripts\run.ps1 materialize --freq 1h` |
| Provider DOWN | Circuit breaker; auto-recovers after cooldown |
| reportv2 --regimes fails | Set `CRYPTO_ANALYZER_ENABLE_REGIMES=1`, run Phase 3 migrations, then regime materialize |
| Verify fails | Run `doctor`; ensure venv active; fix ruff/pytest as indicated |

---

## License

MIT License. See [LICENSE](LICENSE).
