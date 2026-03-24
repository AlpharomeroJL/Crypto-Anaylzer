# Coinbase Majors Live-Data + Signal Upgrade (Phase 1.3)

This case study documents a methodology and platform-surface upgrade on the majors/CEX track.

Phase 1.3 is not an alpha claim. It is a credibility-focused upgrade in:
- live market-data freshness capability (public websocket path),
- majors signal-path breadth (second active majors-compatible path),
- strict validation evidence on the same public research surface.

## 1) What was run

- Live-feed liveness check (public Coinbase websocket, market-data only):
  - `python -m crypto_analyzer venue-sync ws-live --channel market_trades --run-seconds 35 --status-interval-sec 10`
  - Observed health sample from run logs: `messages=211`, `ticks=1433`, `reconnects=0`, `last_msg_age_s=0.0`, `feed_lag_s=0.8`, `bars_flushed=0`.
- Strict majors rerun:
  - `python -m crypto_analyzer reportv2 --universe majors --freq 1h --signals clean_momentum,value_vs_beta --portfolio advanced --walk-forward-strict --reality-check --execution-evidence --out-dir reports/reportv2_majors_phase1_3_ws_sigbreadth_strict`
- Primary artifact root:
  - `reports/reportv2_majors_phase1_3_ws_sigbreadth_strict`

## 2) What changed from Phase 1.2

- Added a public websocket majors market-data path (`venue-sync ws-live`) in the Coinbase venue layer.
- Enabled and verified a second majors-compatible active signal path (`value_vs_beta`) alongside `clean_momentum`.
- Reran strict majors validation with both active paths and generated full strict artifacts.
- Maintained explicit majors/DEX separation (majors scope hashes `venue_bars_1h` and `venue_products`; no DEX table blending).

## 3) Why this matters

- Improves operator visibility into live-feed freshness/continuity on majors data ingestion.
- Expands majors research surface from effectively one active path to two active paths with explicit evidence files.
- Keeps strict validation discipline intact (lineage identifiers, fold-causality attestation, reality-check outputs, execution-evidence outputs).

## 4) What this artifact proves

- A complete strict majors Phase 1.3 run exists with concrete lineage:
  - `run_id`: `c5d8ab1c96532bff`
  - `run_instance_id`: `832e008d05faeb10`
  - `run_key`: `668b5e2e04c880de`
  - `dataset_id_v2`: `6324b3b258ec05d0`
- The strict run used majors scope only (`dataset_hash_scope`: `["venue_bars_1h", "venue_products"]`).
- Fold-causality enforcement checks are attested true:
  - `train_only_fit_enforced`, `no_future_rows_in_fit`, `purge_applied`, `embargo_applied`.
- Second signal path was genuinely active:
  - `validation_bundle_clean_momentum_832e008d05faeb10.json`
  - `validation_bundle_value_vs_beta_832e008d05faeb10.json`
  - `research_v2_20260324_0830.md` includes diagnostics for both signals.

## 5) What it still does not prove

- It does **not** prove durable alpha.
- It does **not** prove production trading readiness.
- It does **not** prove live execution quality or realized PnL.
- It does **not** imply majors findings transfer to DEX.
- Websocket liveness evidence is market-data freshness evidence only, not execution-system validation.

## 6) Key evidence artifacts and lineage

- Phase 1.3 report:
  - `reports/reportv2_majors_phase1_3_ws_sigbreadth_strict/research_v2_20260324_0830.md`
- Manifest:
  - `reports/reportv2_majors_phase1_3_ws_sigbreadth_strict/manifests/c5d8ab1c96532bff.json`
- Fold-causality attestation:
  - `reports/reportv2_majors_phase1_3_ws_sigbreadth_strict/fold_causality_attestation.json`
- Validation bundles:
  - `reports/reportv2_majors_phase1_3_ws_sigbreadth_strict/csv/validation_bundle_clean_momentum_832e008d05faeb10.json`
  - `reports/reportv2_majors_phase1_3_ws_sigbreadth_strict/csv/validation_bundle_value_vs_beta_832e008d05faeb10.json`
- Reality Check:
  - `reports/reportv2_majors_phase1_3_ws_sigbreadth_strict/csv/reality_check_summary_rcfam_e4445426efc86abf.json`
  - `reports/reportv2_majors_phase1_3_ws_sigbreadth_strict/csv/reality_check_null_max_rcfam_e4445426efc86abf.csv`
- Execution evidence:
  - `reports/reportv2_majors_phase1_3_ws_sigbreadth_strict/csv/execution_evidence_clean_momentum_832e008d05faeb10.json`
  - `reports/reportv2_majors_phase1_3_ws_sigbreadth_strict/csv/capacity_curve_clean_momentum_832e008d05faeb10.csv`
  - `reports/reportv2_majors_phase1_3_ws_sigbreadth_strict/csv/execution_evidence_value_vs_beta_832e008d05faeb10.json`
  - `reports/reportv2_majors_phase1_3_ws_sigbreadth_strict/csv/capacity_curve_value_vs_beta_832e008d05faeb10.csv`
- Baseline comparator:
  - `docs/case_studies/coinbase_majors_strict_validation_phase1_2.md`

## 7) Main caveats

- Statistical outcomes remain weak/mixed:
  - Both signal portfolios show negative Sharpe in this run.
  - HAC mean return is non-significant.
  - Reality Check p-value is non-significant (`0.5174`).
- Websocket probe duration was short; it demonstrated feed liveness/lag visibility but did not span an hourly close in that probe (`bars_flushed=0`).
- This artifact is a methodology/evidence upgrade, not a performance milestone.

## 8) Recommended next step

- Publish this as a Phase 1.3 evidence-upgrade companion to Phase 1.2.
- Add a side-by-side evidence table (Phase 1.2 vs 1.3) emphasizing:
  - lineage IDs,
  - strict artifact completeness,
  - active signal set breadth,
  - live-feed health visibility fields.
- Run a longer fixed-window repeat with unchanged strict settings to test stability over time.
