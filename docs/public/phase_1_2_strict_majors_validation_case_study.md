# Crypto-Analyzer Phase 1.2: Strict Majors Validation Case Study

This public note documents a stricter evidence pass on the centralized-exchange majors track only. It is an evidence-rigor upgrade from Phase 1.1, not an alpha claim.

## What was run

- Strict majors-only validation pipeline on the pre-declared CEX majors universe: `[PRODUCT_IDS_USED]`.
- Public market data ingestion + bar materialization + validation/report pipeline:
  - `[CMD_PRODUCTS_SYNC]`
  - `[CMD_CANDLES_SYNC]`
  - `[CMD_REPORT_STRICT]`
- Execution window (UTC): `[RUN_START_UTC]` to `[RUN_END_UTC]`.
- Run identity and reproducibility markers:
  - `run_key`: `[RUN_KEY]`
  - `run_instance_id`: `[RUN_INSTANCE_ID]`
  - `dataset_id_v2`: `[DATASET_ID_V2]`
  - `engine_version`: `[ENGINE_VERSION]`
  - `config_version`: `[CONFIG_VERSION]`

## What changed from Phase 1.1

- Validation standard moved from baseline benchmarking to stricter, fail-closed evidence checks.
- Provenance requirements were tightened (explicit run identity, dataset fingerprint, and artifact hash lineage).
- Reporting posture is now explicitly split by market domain:
  - **Majors/CEX track** (this artifact)
  - **DEX track** (separate artifacts and conclusions)
- Claims discipline is stricter: no performance language beyond what can be independently reproduced from artifacts.

## Why this matters

- Credibility depends on repeatable evidence, not one-off outcomes.
- Strict lineage and identity controls reduce ambiguity about what dataset, code/config state, and run produced the result.
- Keeping majors and DEX evidence separate prevents accidental mixing of structurally different liquidity/execution regimes.

## What this artifact proves

- A Phase 1.2 strict validation run was executed end-to-end for the stated majors universe and window.
- The output can be traced to concrete, checkable identities (`run_key`, `run_instance_id`, `dataset_id_v2`) and hashed artifacts.
- Independent reviewers can verify row counts, hashes, command lineage, and config/run binding without relying on narrative interpretation.

## What it still does not prove

- It does **not** prove durable alpha.
- It does **not** prove live tradability, realized execution quality, or production PnL.
- It does **not** prove transferability to other venues, universes, or regimes.
- It does **not** merge or generalize DEX behavior into majors conclusions.

## Key evidence artifacts and lineage

- Primary report artifact: `[REPORT_PATH]`
- Manifest / metadata bundle: `[MANIFEST_PATH]`
- Lineage export (if generated): `[LINEAGE_EXPORT_PATH]`
- Artifact integrity:
  - `sha256`: `[ARTIFACT_SHA256]`
- Dataset/run references:
  - `dataset_id_v2`: `[DATASET_ID_V2]`
  - `run_key`: `[RUN_KEY]`
  - `run_instance_id`: `[RUN_INSTANCE_ID]`
  - `family_id` (if Reality Check enabled): `[FAMILY_ID]`
- Reproduction commands:
  - `[REPRO_CMD_1]`
  - `[REPRO_CMD_2]`
  - `[REPRO_CMD_3]`

## Main caveats

- Sample length and regime coverage may still be limited.
- Majors-only evidence improves internal validity but does not provide broad cross-sectional breadth.
- Public endpoint data quality/availability can vary over time.
- Statistical stability remains conditional on window selection and configuration lock.

## Recommended next step

- Pre-register a longer, fixed out-of-sample window and rerun the same strict majors protocol with unchanged validation rules.
- Publish side-by-side Phase 1.1 vs 1.2 evidence tables (identity fields, hashes, row counts, and reproducibility outcomes).
- Continue DEX validation as a parallel, explicitly separate track; only compare tracks at the methodology level, not as pooled alpha evidence.
