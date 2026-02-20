# Operational Runbook: Liqshock Case Study Runner

**Feature:** One-command liquidity-shock-reversion memo + deterministic artifact path + run bundle (working packet + optional immutable snapshot).

---

## One command

```powershell
.\scripts\run.ps1 case_study_liqshock --freq 1h --rc-n-sim 300 --rc-method stationary --rc-avg-block-length 12
```

**Passthrough:** `--freq`, `--out-dir`, `--rc-n-sim`, `--rc-method`, `--rc-avg-block-length`, `--rc-seed`, `--dex-only`, `--min-bars`, `--top10-p10-liq-floor`, `--snapshot`, etc.

**Outputs:**

| Output | Path |
|--------|------|
| Timestamped report | `reports/research_v2_<timestamp>.md` (from reportv2) |
| **Deterministic memo** | `reports/case_study_liqshock_<freq>.md` (e.g. `case_study_liqshock_1h.md`) |
| Working packet (mutable) | `reports/case_study_liqshock_latest/` (run-id consistent: memo + RC summary + **best variant** capacity curve + execution evidence JSON + `run_metadata.json`) |
| Snapshot (immutable) | `reports/case_study_liqshock_runs/<run_id>/` (when `--snapshot` is passed; same contents as latest, never overwritten) |
| Capacity curves | `reports/csv/capacity_curve_liqshock_*_<run_id>.csv` (16 per run) |
| Execution evidence | `reports/csv/execution_evidence_liqshock_*_<run_id>.json` (16 per run) |
| RC summary | `reports/csv/reality_check_summary_<family_id>.json` |

**Working packet (run-id consistent):** The wrapper infers `run_id` from capacity-curve files written in the same run (within 15s of the report). It copies only artifacts for that run: RC summary (by modification time window), and the **best** variant (first "Survived" in the BH table, or first variant if none survived) — one capacity curve CSV + one execution evidence JSON. It also writes `run_metadata.json` (run_id, freq, rc params, timestamp_utc, git_commit). The folder is cleared before each copy so it always matches the run you just executed.

---

## Snapshot semantics (immutable research snapshot)

Pass `--snapshot` to create a copy that is **never overwritten**:

```powershell
.\scripts\run.ps1 case_study_liqshock --freq 1h --rc-n-sim 500 --snapshot
```

This creates `reports/case_study_liqshock_runs/<run_id>/` with the same contents as `case_study_liqshock_latest/`. That folder is the **immutable research snapshot** for that run. Archive or share it as the run bundle (zip if needed). No cover note or external process is implied; the memo and `run_metadata.json` provide reproducibility details.

**To share or archive a run:** Zip `reports/case_study_liqshock_latest/` (current run) or `reports/case_study_liqshock_runs/<run_id>/` (if you used `--snapshot`). Single folder contains: memo, RC summary, best-variant capacity curve + execution evidence JSON, `run_metadata.json`, and `README.txt`. Statistical stability improves with larger universe/history; the memo and run metadata state the evaluation setup.

---

## Pre-release checklist (before tagging)

- [ ] `.\scripts\run.ps1 case_study_liqshock --freq 1h` completes with exit 0.
- [ ] `reports/case_study_liqshock_1h.md` exists and contains:
  - "Page 1 — Executive-Level Signal Framing"
  - "False Discoveries Rejected"
  - "Top 10 most valuable pairs"
- [ ] `reports/case_study_liqshock_latest/` contains memo + RC summary JSON + at least one capacity curve CSV.
- [ ] `python -m pytest tests/test_reportv2_case_study_liqshock.py tests/test_signals_xs_liqshock.py -q` passes.
- [ ] Default report unchanged: `.\scripts\run.ps1 reportv2 --freq 1h --signals clean_momentum` still produces "Research Report v2 (Milestone 4)".

---

## References

- [Research validation workflow](../research_validation_workflow.md) — exploratory vs full-scale runs, validation readiness criteria, run_id and snapshot semantics.
- README: [Expanded-Universe Validation Workflow](../../README.md) — CLI cheatsheet, operational checklist, diagnostics.
