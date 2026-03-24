# Coinbase Majors Benchmark (Phase 1.1)

## 1) What was run

This artifact summarizes a completed `reportv2` benchmark run in majors mode using the expanded Coinbase panel.

- Command profile: `reportv2 --universe majors --freq 1h --signals clean_momentum,value_vs_beta --portfolio advanced`
- Output root: `reports/reportv2_majors_phase1_1`
- Primary report: `reports/reportv2_majors_phase1_1/research_v2_20260324_0725.md`
- Manifest: `reports/reportv2_majors_phase1_1/manifests/9b1749621b6ebcdc.json`

## 2) Universe and data source

- Universe mode: `majors` (explicit, not DEX universe mode)
- Data source: Coinbase Advanced Trade public REST pipeline into `venue_products` and `venue_bars_1h`
- Configured majors panel size: 9 assets (BTC, ETH, SOL + 6 additional majors)
- Effective report coverage: `n_assets=9`, `n_bars=4219`
- Manifest data window:
  - start: `2025-03-01 01:00:00+00:00`
  - end: `2026-03-24 00:00:00+00:00`

## 3) Why this matters

This is a stronger benchmark surface than the earlier 3-asset majors runs because it increases cross-sectional breadth while keeping clear lineage:

- Same SQLite system-of-record
- Same Coinbase venue tables
- Same explicit majors mode in `reportv2`
- No DEX/CEX semantic blending

The result is better public evidence that the majors research workflow is real, reproducible, and scoped correctly.

## 4) What the artifact proves

This run provides evidence of infrastructure and workflow credibility:

- End-to-end majors benchmark execution succeeds on a 9-asset panel.
- Run identity and provenance are recorded (`run_id`, `run_instance_id`, `run_key`, commit, spec version).
- Dataset lineage is explicit and venue-scoped:
  - `dataset_id_v1`: `b57bf0dda072809c`
  - `dataset_id_v2`: `ec1d43e36254e830`
  - `dataset_hash_scope`: `["venue_bars_1h", "venue_products"]`
- Validation artifacts are emitted for the evaluated signal:
  - `csv/validation_bundle_clean_momentum_e0ecd361011471f9.json`
  - IC series and decay CSVs
  - stats and health summaries

## 5) What it does not prove

This artifact does **not** prove deployable alpha.

Specifically:

- It does not establish robust predictive performance.
- It does not establish production execution readiness.
- It does not validate trading infrastructure (no auth/trading/websocket stack involved).
- It does not claim DEX and majors are interchangeable research universes.

## 6) Key lineage/reproducibility evidence

Evidence files:

- `reports/reportv2_majors_phase1_1/research_v2_20260324_0725.md`
- `reports/reportv2_majors_phase1_1/manifests/9b1749621b6ebcdc.json`
- `reports/reportv2_majors_phase1_1/stats_overview.json`
- `reports/reportv2_majors_phase1_1/health/health_summary.json`
- `reports/reportv2_majors_phase1_1/csv/validation_bundle_clean_momentum_e0ecd361011471f9.json`

Manifest-backed identifiers:

- `run_id`: `9b1749621b6ebcdc`
- `run_instance_id`: `e0ecd361011471f9`
- `run_key`: `3470bacdd14f2f72`
- `engine_version`: `ac1e277`
- `research_spec_version`: `5.0`

## 7) Main caveats

This run should be interpreted conservatively:

- Orthogonalization did not proceed (`Need at least 2 signals for orthogonalization`).
- Effective evaluation was narrow (`you tested 1 signals and 1 portfolios`).
- PBO proxy is unavailable in this run (`Too few splits for PBO`).
- Current observed signal quality is weak in this run (negative Sharpe and non-significant HAC mean-return test).
- Walk-forward attestation and execution-evidence curves are not enabled in this specific artifact (`walk_forward_used=false`, `capacity_curve_written=false`).

## 8) Recommended next step for the platform

Keep this artifact as a public benchmark milestone, then run a follow-up majors validation pass with stricter evidence settings on the same universe:

- enable walk-forward strict mode and attestation
- enable reality-check and execution-evidence outputs
- keep majors/DEX separation explicit in all reporting

This keeps credibility high by improving evidence quality without changing architecture boundaries.
