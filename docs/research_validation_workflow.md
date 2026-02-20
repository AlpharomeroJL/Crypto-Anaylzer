# Research Validation Workflow

This document describes the stack-native workflow for producing **reproducible research memos and artifacts** from ingestion through to immutable run snapshots. The pipeline is: **ingestion → materialize → research report v2 → case-study renderer → artifacts keyed by `run_id` → immutable research snapshot**.

## What it is

- **Reproducible research memo + artifacts:** The system runs reportv2 with a case-study template (e.g. liqshock), writes a memo and supporting artifacts (capacity curves, Reality Check summary, execution evidence), and optionally snapshots the run under a deterministic `run_id`.
- **Internal research execution surface:** No code behavior or CLI flags are tied to external processes; the docs describe how to run exploratory vs full-scale validation and how to interpret diagnostics.

## Key concepts

| Concept | Meaning |
|--------|--------|
| **run_id** | Stable hash derived from the run (e.g. from capacity-curve filenames). Keys artifact paths and the snapshot folder. |
| **RC family_id** | Reality Check family (signal×horizon); used in RC cache and for grouping null distributions. |
| **Determinism** | Same inputs and config → same `run_id` and artifact hashes. Use `CRYPTO_ANALYZER_DETERMINISTIC_TIME` for reproducible reruns. |
| **Snapshot vs working packet** | **Snapshot:** `reports/case_study_liqshock_runs/<run_id>/` — immutable; created with `--snapshot`; never overwritten. **Working packet:** `reports/case_study_liqshock_latest/` — mutable; overwritten each run; memo + RC summary + best-variant capacity curve + execution evidence + `run_metadata.json`. |

## Typical workflows

### Exploratory validation run

- **Goal:** Cheap, frequent checks while building data (pairs + history). Low RC sims, low `--min-bars` so diagnostics stay informative.
- **When:** Early ramp, or when you want to confirm returns/bars/diagnostics without committing a snapshot.
- **Command (example):**

```powershell
.\scripts\run.ps1 case_study_liqshock --freq 1h --dex-only --min-bars 25 --rc-n-sim 50 --rc-method stationary --rc-avg-block-length 24
```

- **Watch:** returns columns, returns date range, bars unique pair_ids, bars date range, bars columns matched (%).
- **No `--snapshot`:** Only `case_study_liqshock_latest/` is updated.

### Full-scale validation run

- **Goal:** Higher statistical resolution and a frozen run bundle. Use when diagnostics meet validation readiness criteria (see below).
- **When:** You have sufficient pairs and history and want an immutable research snapshot.
- **Command (example):**

```powershell
.\scripts\run.ps1 case_study_liqshock --freq 1h --dex-only --min-bars 1000 --rc-n-sim 1000 --rc-method stationary --rc-avg-block-length 24 --snapshot
```

- **Result:** Same outputs as above, plus a copy under `reports/case_study_liqshock_runs/<run_id>/` that is never overwritten. Archive or share that folder as the run bundle.

## Validation readiness criteria

Use these to decide when to run a **full-scale validation run** (high min-bars, high RC sims, `--snapshot`) rather than an exploratory run:

- **bars unique pair_ids** ≥ 25  
- **bars date range** ≥ ~180 days (or your chosen minimum history)  
- **bars columns matched** ≥ 25 (with `--dex-only`, the usable intersection)  
- Top 10 table has enough eligible pairs (e.g. 5–10) given p10 floor and missing%

Then you can expect finite Sharpe, non-NaN raw p-values, and plausible BH outcomes. Small sample size and short history remain limitations; the memo and run metadata should reflect that.

## Data and materialize

- **Breadth at materialize:** Use `--no-snapshot-filters` when you need bars for many pairs (e.g. expanded universe); bars are built from all snapshot rows. Research-time screens (Top 10 p10 floor, missing%, min-bars) remain the place to enforce quality.
- **No forward-looking liquidity:** The filter bypass does not introduce forward-looking liquidity; Top 10 missing% and p10-liquidity floor protect inference.

## Data provenance

Historical imports or backfills are supported as a data-regime change for validation (e.g. to reach ≥180d history or broader cross-section). The workflow is unchanged: ingest or load the data, materialize bars, then run exploratory or full-scale validation as above. Record provenance in run metadata or notes (e.g. source of history, import date, any filters applied) so runs remain auditable.

## Walk-forward

Walk-forward splitting is supported; a given run uses the full evaluation window unless walk-forward mode is enabled. The memo and run metadata should state the evaluation setup.

## References

- **README:** [Expanded-Universe Validation Workflow](../README.md#expanded-universe-validation-workflow-case-study-liqshock) (CLI cheatsheet, operational checklist, diagnostics).
- **Runbook:** [Operational Runbook: Liqshock Case Study Runner](spec/case_study_liqshock_release.md) (one-command usage, outputs, snapshot semantics, pre-release checklist).
