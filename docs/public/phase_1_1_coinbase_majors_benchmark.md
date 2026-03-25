# Crypto-Analyzer Phase 1.1: Coinbase Majors Benchmark

This note documents what was executed for the Phase 1.1 Coinbase majors benchmark, what evidence exists, and how to interpret results without overclaiming.

## What was run

- Venue product sync (public Coinbase Advanced Trade REST): `[CMD_PRODUCTS_SYNC]`
- Venue candle backfill (1h bars): `[CMD_CANDLES_SYNC]`
- Majors-only benchmark report: `[CMD_REPORT]`
- Execution window (UTC): `[RUN_START_UTC]` to `[RUN_END_UTC]`
- Software/config identity:
  - `engine_version`: `[ENGINE_VERSION]`
  - `config_version`: `[CONFIG_VERSION]`
  - `run_instance_id` or `run_id`: `[RUN_INSTANCE_ID]`

## Universe and data source

- Universe: Coinbase USD majors configured in `config.yaml` at `venue.coinbase_advanced.product_ids`.
- Product set used in this run: `[PRODUCT_IDS_USED]` (example format: `BTC-USD, ETH-USD, SOL-USD`).
- Source: Coinbase Advanced Trade **public** market data endpoints (no API keys, no private endpoints).
- Local storage:
  - Product metadata table: `venue_products`
  - 1h OHLCV table: `venue_bars_1h`
- Frequency: 1h bars only for this benchmark.

## Why this matters

- Establishes a reproducible, venue-specific baseline on highly traded pairs before expanding to broader universes.
- Demonstrates that the research pipeline can ingest, materialize, and report on centralized exchange data with deterministic lineage controls.
- Provides a public credibility checkpoint: transparent inputs, explicit limitations, and repeatable commands.

## What artifact proves

- The benchmark was executed end-to-end for the stated universe and period.
- The reported outputs are tied to concrete run and dataset identities.
- The SQLite records and report artifacts can be independently re-checked for row counts, hashes, and command reproducibility.

Primary evidence slots:

- Report artifact path: `[REPORT_PATH]`
- Manifest/metadata path: `[MANIFEST_PATH]`
- Dataset fingerprint:
  - `dataset_id`: `[DATASET_ID]`
  - `dataset_id_v2` (if present): `[DATASET_ID_V2]`
- Artifact hash:
  - `sha256`: `[ARTIFACT_SHA256]`
- Row count checks:
  - `venue_products`: `[ROWCOUNT_VENUE_PRODUCTS]`
  - `venue_bars_1h`: `[ROWCOUNT_VENUE_BARS_1H]`

## What it does not prove

- It does **not** prove durable alpha or production trading edge.
- It does **not** prove transferability outside the tested pairs, venue, or date range.
- It does **not** include authenticated execution, order placement, fees/slippage reality checks, or live PnL validation.
- It does **not** establish DEX/CEX combined cross-sectional behavior in one benchmark.

## Key lineage/repro evidence

- Reproduction commands:
  - `[REPRO_CMD_1]`
  - `[REPRO_CMD_2]`
  - `[REPRO_CMD_3]`
- Config snapshot path used for run: `[CONFIG_SNAPSHOT_PATH]`
- Environment fingerprint:
  - Python version: `[PYTHON_VERSION]`
  - OS/runtime: `[RUNTIME_INFO]`
- DB path used: `[DB_PATH]`
- Optional provenance graph artifacts:
  - `run_key`: `[RUN_KEY]`
  - `family_id` (if applicable): `[FAMILY_ID]`
  - lineage table or export path: `[LINEAGE_EXPORT_PATH]`

## Main caveats

- Sample depth may be limited by available historical bars and listing history of each product.
- Results can be sensitive to benchmark window selection and market regime mix.
- Majors-only evidence has lower cross-sectional breadth than broader universe tests.
- Public endpoint data quality/availability can vary by time and exchange-side conditions.

## Recommended next step

- Run the same benchmark on a longer, pre-declared window and publish side-by-side stability checks (same commands, fixed config, new run IDs).
- Add a blinded out-of-sample holdout period and report whether the directional conclusions persist.
- If conclusions remain stable, extend to a clearly separated Phase 1.2 comparison (additional venues or expanded majors set) with the same lineage requirements.
