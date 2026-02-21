# Stats stack upgrade — Acceptance criteria (Definition of Done per PR)

Use this checklist per PR. Matches existing patterns: reportv2 outputs + JSON/CSV artifacts + pytest coverage + deterministic seeds + no contract breaks.

---

## Scope + non-goals

- **Additive-only artifacts; no breaking changes to reportv2 contracts.** New fields and files only; existing filenames and required keys stay as-is.
- **No claim of full academic calibration unless explicitly stated.** Methods are implementation-aligned and documented; reviewers should not assume publication-grade calibration unless the doc or code says so.
- **RW is FWER gate; BH/BY is FDR discovery; both co-exist.** Romano–Wolf is for strict promotion gating (family-wise); Benjamini–Hochberg / Benjamini–Yekutieli remain for discovery. Do not remove or replace BH/BY when adding RW.

---

## CLI contract (hard requirements)

Intent must be unambiguous. **Do not infer intent from default numeric values** (e.g. "50" must not be treated as "user said 50" vs "use auto").

| Flag | Semantics | Default |
| ---- | --------- | ------- |
| `--n-trials` (auto or int) | `auto` = compute Neff from strategy returns and use for DSR; int = use that value | `auto` |
| `--hac-lags` (auto or int) | `auto` = apply lag rule (e.g. NW heuristic); int = use that L | `auto` |
| `--pbo-cscv-blocks` | Number of sequential blocks S for CSCV | e.g. 16 |
| `--pbo-cscv-max-splits` | Cap on enumerated splits; beyond this, random-sample with seed | e.g. 20000 |
| `--pbo-metric` | Metric inside CSCV: `mean` or `sharpe` | e.g. `mean` |

Parse `--n-trials` and `--hac-lags` as string; treat only the literal `"auto"` (or agreed sentinel) as auto; any numeric string or int is explicit user value.

---

## Minimum data thresholds

Reportv2 must not output nonsense when series are too short. Treat **"insufficient data"** as a first-class output state in artifacts (record reason, omit or null the statistic).

| Component | Minimum | When below threshold |
| --------- | ------- | -------------------- |
| **HAC** | n ≥ 30 | Report null/omit with reason (e.g. `hac_skipped_reason: "n < 30"`) |
| **CSCV** | T ≥ S × min_block_len (e.g. 4 obs per block) and J ≥ 2 | Skip CSCV; record reason in meta |
| **Break scan** (sup-Chow/sup-Wald) | n ≥ 100 | Skip scan or report null; CUSUM may use a lower n if documented |
| **CUSUM** | Document minimum (e.g. n ≥ 20) | Below: report null with reason |

Artifacts must include a clear indicator when a statistic was skipped due to insufficient data (e.g. `null` + a `*_reason` or `*_skipped` key).

---

## Exact artifact keys (single source of truth)

Use these exact JSON key names to avoid drift across PRs.

### stats_overview.json

- `n_trials_used`, `n_trials_user` (null if auto, else int), `n_trials_eff_eigen` (null if user-specified), `n_trials_eff_inputs_total`, `n_trials_eff_inputs_used`
- `hac_lags_used`, `hac_skipped_reason` (when skipped), `t_hac_mean_return`, `p_hac_mean_return` (null when skipped)
- `pbo_cscv`, `pbo_cscv_blocks`, `pbo_cscv_total_splits`, `pbo_cscv_splits_used`, `pbo_metric`; when skipped: `pbo_cscv_skipped_reason`
- `rw_enabled` (bool), `rw_alpha` (float, when applicable)
- `break_diagnostics_written`, `break_diagnostics_skipped_reason` (when no series written)
- `capacity_curve_written`, `non_monotone_capacity_curve_observed` (bool, optional)

### break_diagnostics.json

- Top-level: `series` → per-series list of test entries.
- Per test entry: `series_name`, `test_name`, `stat`, `p_value`, `break_suspected`, `estimated_break_index`, `estimated_break_date`, `calibration_method`; when skipped: `skipped_reason` (stat/p_value null, break_suspected false).

### reality_check_summary_*.json (additions)

- `rw_adjusted_p_values` — only when RW enabled; object/dict hypothesis_id → adjusted p-value, or empty when disabled.
- `rc_p_value`, `observed_max`, `n_sim`, `hypothesis_ids`, `rc_metric`, `rc_method`, `rc_avg_block_length` (existing).
- When RW enabled: `rw_alpha`, `bootstrap_B`, `bootstrap_method`, `block_length` (or equivalent) so reviewers can reproduce.

---

## 1) Neff (effective trials) + plumb into DSR default

### 1.1 Functional

- [ ] `effective_trials_eigen(C)` exists and returns a finite scalar Neff >= 1.
- [ ] Handles:
  - identity correlation → Neff ≈ m
  - rank-1 / collinear → Neff ≈ 1
  - near-PSD / non-PSD (numerical) → stable via eigenvalue clipping or PSD projection.
- [ ] reportv2 supports `--n-trials auto|<int>` (or equivalent explicit "auto" sentinel).
- [ ] When **auto**:
  - builds strategy return matrix R[T,J] from `portfolio_pnls` (aligned index)
  - computes C = corr(R) and Neff
  - passes `n_trials_used = Neff` into DSR
- [ ] When explicit `--n-trials <int>`:
  - `n_trials_used` equals the user int (no Neff computation required)

### 1.2 Artifact / audit

- [ ] Report output includes (in table + JSON meta):
  - `n_trials_user` (null if auto)
  - `n_trials_eff_eigen` (null if user-specified)
  - `n_trials_used` (always present)

### 1.3 Tests

- [ ] Unit tests for `effective_trials_eigen` (identity, rank-1, noisy correlation).
- [ ] Integration test: running reportv2 with >=2 strategies and `--n-trials auto` yields meta fields populated.

---

## 2) HAC-adjusted inference (Newey–West)

### 2.1 Functional

- [ ] Implements:
  - `newey_west_lrv(x, L)` (Bartlett weights)
  - `hac_tstat_mean(x, L)`
  - `p_hac` computed and reported (normal approx is fine initially; document it)
- [ ] reportv2 displays `t_hac` and `p_hac` for at least:
  - main portfolio return series (and optionally IC series if available)
- [ ] CLI supports `--hac-lags auto|<int>` and the chosen L is recorded.
- [ ] **Minimum data**: require n >= 30 for HAC; otherwise report null with reason (e.g. `hac_skipped_reason: "n < 30"`).

### 2.2 Artifact / audit

- [ ] Output includes:
  - `hac_lags_used`
  - `t_hac_mean_return`, `p_hac_mean_return`
  - (optional) HAC CI for mean return; if you show "implied Sharpe CI," label it explicitly as derived from mean inference.

### 2.3 Tests

- [ ] Deterministic AR(1) synthetic series:
  - IID t-stat differs from HAC t-stat for L>0
  - HAC variance increases under positive autocorrelation
- [ ] Edge cases:
  - short series (n < 3L) handled gracefully (cap L or fall back)

---

## 3) Romano–Wolf stepdown (replace stub)

### 3.1 Functional

- [ ] With `CRYPTO_ANALYZER_ENABLE_ROMANOWOLF=1`:
  - does not raise
  - returns non-empty `rw_adjusted_p_values` aligned to hypotheses
- [ ] Uses the existing joint bootstrap null matrix (no extra bootstrap passes).
- [ ] Stepdown implemented as maxT / max-statistic:
  - orders hypotheses by observed statistic
  - at each step uses max across remaining hypotheses per bootstrap draw
  - computes adjusted p-values with (1 + count)/(B+1)
- [ ] Adjusted p-values are monotone non-decreasing in stepdown order.

### 3.2 Artifact / audit

- [ ] `reality_check_summary_*.json` includes:
  - `rw_adjusted_p_values` only when enabled (or empty dict when disabled, whichever you standardize)
  - fields describing: alpha, B, bootstrap method, block length

### 3.3 Tests

- [ ] Deterministic tests with controlled null matrices:
  - (a) observed >> null → rejects
  - (b) observed <= null max → no rejects
  - (c) mixed case verifying stepdown stop behavior
- [ ] Ensures legacy RC p-value output unchanged when RW disabled.

---

## 4) True CSCV PBO (canonical) alongside proxy

### 4.1 Functional

- [ ] Implements `pbo_cscv(R, S, seed, max_splits=..., metric=...)`.
- [ ] Default S is safe (e.g. 16) and doesn't explode combinatorially.
- [ ] If choose(S, S/2) exceeds max_splits, algorithm:
  - random-samples combinations deterministically via seed.
- [ ] reportv2:
  - continues to compute `pbo_proxy` as today (backward compatibility)
  - adds `pbo_cscv` when J >= 2 and T >= S × min_block_len (e.g. 4 obs per block); otherwise skips with reason in meta
  - records S, n_splits_used, metric
- [ ] **Minimum data**: CSCV requires T >= S × min_block_len and J >= 2; below threshold, skip and record reason (first-class "insufficient data" in artifacts).

### 4.2 Artifact / audit

- [ ] Adds to JSON meta:
  - `pbo_cscv`, `pbo_cscv_blocks`, `pbo_cscv_splits_used`, `pbo_metric`
  - Optional: store summary stats of λ distribution (mean, std, frac<0)

### 4.3 Tests

- [ ] Unit tests:
  - Construct R where the in-sample winner tends to be out-of-sample loser → PBO high
  - Construct R where winner generalizes → PBO low
  - Construct R with identical strategies → PBO ~ 0.5 (within tolerance)
- [ ] Integration test: reportv2 on multi-strategy run emits both PBO fields.

---

## 5) Structural break diagnostics (CUSUM + single-break scan)

### 5.1 Functional

- [ ] Adds break tests module with at least:
  - CUSUM mean-shift (variance via HAC or bootstrap)
  - single-break scan (sup-Chow/sup-Wald style) returning argmax break date/index
- [ ] reportv2 runs breaks on:
  - IC series (if present), and/or
  - portfolio net returns
- [ ] Produces "break flags" not just plots:
  - `break_suspected` boolean
  - `p_value`
  - `estimated_break_date` (if scan)
- [ ] **Minimum data**: require n >= 100 for single-break scan; CUSUM may use a smaller minimum (e.g. n >= 20) if documented. Below threshold: report null with reason.

### 5.2 Artifact / audit

- [ ] Writes `break_diagnostics.json` (or embeds in report meta) with:
  - series name, test name, stat, p, suspected flag, break date/index
  - HAC settings or bootstrap settings used for calibration

### 5.3 Tests

- [ ] Synthetic series with mean shift at known index:
  - scan returns break near that index
  - p-value becomes small when shift large enough
- [ ] No-shift series:
  - p-values not systematically tiny (sanity check)

---

## 6) Capacity curve realism (Sharpe vs capital)

### 6.1 Functional

- [ ] Keeps existing CSV contract unchanged:
  - must include `notional_multiplier`, `sharpe_annual`
- [ ] Enhances cost model size-dependence:
  - slippage/impact increases with multiplier (participation or proxy)
  - Recomputes net returns per multiplier and then Sharpe per multiplier.
- [ ] Allows optional extra output columns (additive only):
  - `mean_ret_annual`, `vol_annual`, `avg_turnover`, `est_cost_bps`, etc.
- [ ] `--execution-evidence` behavior unchanged (still writes CSV + JSON path).

### 6.2 Artifact / audit

- [ ] Capacity CSV includes the original columns + any additional columns.
- [ ] Execution evidence JSON includes:
  - config parameters used (impact model, spreads, participation assumptions)
  - link to capacity curve CSV path

### 6.3 Tests

- [ ] Existing e2e test continues to pass (at minimum asserts required columns exist).
- [ ] **Monotonicity (default synthetic case)**: with constant gross returns and costs increasing with multiplier, net Sharpe is **non-increasing** in multiplier. This is the required behavior in the synthetic test.
- [ ] **Real data**: if in real data the capacity curve has Sharpe increasing with multiplier, do **not** force monotone; instead set `non_monotone_capacity_curve_observed: true` in `stats_overview.json` (see Exact artifact keys).

---

## Repo-wide "done" gates (for the whole upgrade)

- [ ] `pytest -q` green
- [ ] Ruff/format checks green
- [ ] One end-to-end reportv2 run produces:
  - RC summary (and RW if enabled)
  - Overfitting section includes: DSR (auto trials), BH/BY, PBO proxy + CSCV, HAC stats
  - break diagnostics artifact
  - capacity curve + execution evidence artifacts
- [ ] No breaking changes to existing artifact filenames/required fields (additive only).

---

## Golden run (canonical "ship it" command)

Single invocation that exercises the full upgrade. Reviewers run this and verify expected outputs exist.

**Command (PowerShell, from repo root):**

```powershell
$env:CRYPTO_ANALYZER_ENABLE_ROMANOWOLF="1"
.\scripts\run.ps1 reportv2 --db <path_to_db> --out-dir reports_golden --reality-check --execution-evidence --n-trials auto --hac-lags auto --signals clean_momentum,value_vs_beta,momentum_24h
```

(Adjust `--db`, `--out-dir`, `--signals` to match your environment; use at least two signals so Neff and CSCV see J >= 2.)

**Expected output files (under `reports_golden/` or equivalent):**

- `csv/reality_check_summary_<family_id>.json` — RC p-value, and when RW enabled: `rw_adjusted_p_values`, bootstrap params
- `csv/break_diagnostics.json` — break tests per series (IC, net returns)
- `stats_overview.json` — n_trials_used, hac_lags_used, pbo_cscv*, HAC stats, rw_enabled; optional `non_monotone_capacity_curve_observed`
- `csv/capacity_curve_<signal>_<run_id>.csv` — `notional_multiplier`, `sharpe_annual` (+ optional columns)
- `csv/execution_evidence_<signal>_<run_id>.json` — capacity_curve_path, cost config
- Report markdown (e.g. `research_v2_*.md`) with Overfitting section: DSR (auto trials), PBO proxy + PBO CSCV, HAC t/p, RC (and RW if enabled)

**Success:** All of the above exist; `pytest -q` and `ruff check .` are green.
