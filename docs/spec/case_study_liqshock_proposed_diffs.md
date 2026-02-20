# Case Study Liqshock: Proposed Diffs (Post-Plan)

**Canonical spec for case-study execution. Do not change during execution unless something truly blocks.**

This document lists the **proposed file changes** that result from implementing the case study plan (guardrails, concrete slices, acceptance criteria, "most valuable" definition). It is the diff summary you can expect after implementation.

**Must-fix before coding:** §E2. **Strongly recommended (high ROI):** §E3.

---

## A) Guardrails (already in plan as §0)

- Implement only what [docs/case_study_liqshock_spec.md](case_study_liqshock_spec.md) requires; no refactor of unrelated code.
- reportv2 default behavior unchanged unless `--case-study liqshock` is passed.
- Additive changes only; no breaking changes to `crypto_analyzer/data.py` public API; use existing `load_bars` as contract.
- All new outputs keyed by run_id / existing artifact patterns.

---

## B) Concrete implementation slices → file-level diffs

### 1. New file: `docs/case_study_liqshock_spec.md`

- **Add** spec: 16-variant grid (N, winsor_p, clip), memo headings (Page 1/2/3), artifact patterns (run_id keyed), tone rules, Alpha Case Study Narrative reference. Single source of truth for the case study.

### 2. `crypto_analyzer/signals_xs.py`

- **Add** function to compute liquidity-shock reversion signal (single variant): inputs `liquidity_panel`, optional `roll_vol_panel`; **clip liquidity to floor (e.g. 1.0) before log**; for roll_vol normalization use `replace(0, np.nan)` and/or `clip(lower=eps)` (see E2 §2). dlogL, winsorize, zscore, negate; align to returns index/columns.
- **Add** variant generator returning `dict[str, pd.DataFrame]` with 16 deterministic keys (e.g. `liqshock_N6_w0.01_clip3`, ...).
- **No** changes to existing function signatures or behavior of `zscore_cross_section`, `winsorize_cross_section`, `clean_momentum`, `value_vs_beta`, etc.

### 3. `cli/research_report_v2.py`

- **Add** bars load path: after `get_research_assets()`, call `load_bars(...)`. Build `pair_id = chain_id:pair_address`; **keep only bars whose pair_id is in returns_df.columns** (or pivot then intersect columns with returns_df). Pivot `liquidity_usd` and `roll_vol` to panels; reindex to `returns_df.index` and `returns_df.columns`. In case-study mode **log:** `"returns columns: X, bars columns matched: Y (Z%)"` (E2 §1). Only run when `"liquidity_shock_reversion"` in parsed `--signals`.
- **Inject** liqshock expansion **immediately after** `signals_dict` is built, **before** orthogonalization. When `liquidity_shock_reversion` in signal list, call variant generator and merge 16 DataFrames into `signals_dict`.
- **Add** orthogonalization skip: if original `--signals` is exactly `["liquidity_shock_reversion"]`, set `orth_dict = signals_dict` and skip `orthogonalize_signals()`.
- **Isolate case-study rendering (E3 §7):** collect normal artifacts/metrics as usual; **if case_study:** call **`render_case_study_memo(...)`** (or equivalent) with collected data; **else** existing report builder. No sprinkling of `if args.case_study` across the file.
- **Add** CLI flag `--case-study liqshock`. When set, `render_case_study_memo` (or similar) does:
  - **Header:** determinism boilerplate **plus** Assumptions bullets: *"Execution assumed at t+1 bar (as-of lag 1 bar)."* *"No forward-looking liquidity measures used."* (E2 §10).
  - Page 1/2/3 template; **print fixed grid** (N, winsor_p, clip) and **single headline horizon** (e.g. 1 bar) for BH and executive summary; full horizon table in appendix (E3 §6).
  - **False Discoveries Rejected** table: **Raw Sharpe** = same as run (e.g. --portfolio advanced), OOS; **reuse canonical_metrics** for Sharpe (E2 §3). **Variant set:** `liqshock_variants = [k for k in signals_dict if k.startswith("liqshock_")]`; BH on those only; if other signals present, add sentence *"BH correction is applied to the 16-variant liqshock grid only (case-study mode)."* (E2 §4).
  - **Top 10 most valuable pairs:** use **OOS index only** for event rate and medians; slice liquidity/shock to report evaluation index; define extreme shock from same pre-negation z-score as signal (E2 §5).
  - **Factor-per-fold (E2 §8):** if `--strict-fold-factors` not implemented: always include limitation disclosure; if implemented and enabled: include positive claim.
- **No** change to default report flow when `--case-study` is not passed.

### 4. `scripts/run.ps1`

- **Add** switch case `case_study_liqshock`: invoke reportv2 with `--signals liquidity_shock_reversion --portfolio advanced --execution-evidence --reality-check --case-study liqshock` (or equivalent) and passthrough `--freq`, `--rc-n-sim`, `--rc-method`, `--rc-avg-block-length`, `--out-dir`, etc. After run, **copy or rename** the generated report (timestamped) to a deterministic path, e.g. `reports/case_study_liqshock_<freq>.md` or `reports/case_study_liqshock_1h.md`. Add `case_study_liqshock` to the usage/help text in default branch.

### 5. Tests (E3 §9: make them feasible)

- **New** (e.g. `tests/test_signals_xs_liqshock.py`): unit tests for liqshock — empty liquidity → empty; alignment to returns index/columns; floor/clip before log; no future data in formula.
- **Memo renderer unit test:** pass synthetic `signals_dict`, metrics, and table data into the case-study memo renderer; **assert** output contains required headings and both table sections (False Discoveries Rejected, Top 10).
- **Smoke test:** ensure `--case-study liqshock` triggers the case-study renderer (e.g. correct function called). Full reportv2 e2e with fixture DB is optional; do not block on it.

---

## C) Acceptance criteria (what to show at the end)

After implementation, the following must hold:

1. **Command:**  
   `.\scripts\run.ps1 case_study_liqshock --freq 1h --reality-check --execution-evidence`  
   **produces:**
   - Memo markdown with Page 1/2/3 headings, "False Discoveries Rejected" table, and "Top 10 most valuable pairs" table.
   - Capacity curve CSV and execution evidence JSON (existing pattern: `capacity_curve_<signal>_<run_id>.csv`, `execution_evidence_<signal>_<run_id>.json`).
   - RC summary JSON (`reality_check_summary_<family_id>.json`).

2. **pytest -q** passes (including new signal tests and the integration test for case-study table sections).

---

## D) "Most valuable" in the memo (validation / memo quality)

The Top 10 table should be framed as **most economically meaningful + statistically informative under the hypothesis**. Emphasize in spec and memo text:

- **Stable liquidity** (p10 liquidity).
- **Enough volatility/activity.**
- **Enough shock events** to estimate the effect.
- **Low missingness.**

This positions the memo as research capacity + inference quality, not hype coins.

---

## E) Files touched (summary)

| File | Change |
|------|--------|
| `docs/case_study_liqshock_spec.md` | **New.** Spec: grid, headings, artifacts, tone. |
| `crypto_analyzer/signals_xs.py` | **Add** liqshock single-variant + 16-variant generator. |
| `cli/research_report_v2.py` | **Add** bars load + liquidity panel; inject expansion; orth skip; `--case-study liqshock` template, BH table, Top 10 table, limitation note, determinism boilerplate. |
| `scripts/run.ps1` | **Add** `case_study_liqshock` command; copy/rename memo to deterministic path. |
| `tests/test_signals_xs_liqshock.py` (or similar) | **New.** Unit tests for liqshock alignment/no-leakage. |
| `tests/test_reportv2_case_study_liqshock.py` (or similar) | **New.** Integration test for `--case-study liqshock` table sections. |

**No changes:** `crypto_analyzer/data.py` public API (use `load_bars` only as-is), `db/migrations.py`, provider interfaces, config schema keys.

---

## E2) Must-fix before coding

Implement these before or as part of the main slices; they prevent silent bugs and interview blowbacks.

**1) load_bars() + pair_id must match returns_df.columns**

- The repo has multiple asset_id conventions (DEX pair vs spot). **Only keep bars rows whose pair_id exists in returns_df.columns** before pivoting (or after pivoting use column intersection so the liquidity panel has only columns in returns_df).
- In case-study mode, **log a one-line diagnostic:**  
  `"returns columns: X, bars columns matched: Y (Z%)"`  
  so you never silently get all-NaN signals.

**2) Liquidity log transform needs a floor**

- `log(L_t)` is invalid if L_t <= 0 or missing. In the signal function:
  - **L = liquidity_panel.clip(lower=1.0)** (or 1e-6; $1 is interpretable), then `np.log(L)`.
  - For roll_vol normalization: **roll_vol_panel.replace(0, np.nan)** and/or **clip(lower=eps)** before use so division is safe.

**3) Define "Raw Sharpe" in the BH table explicitly**

- Reportv2 has multiple return series / portfolio modes. **"Raw Sharpe" in the False Discoveries Rejected table must be the same portfolio config used in the run (e.g. --portfolio advanced) and must be OOS.**
- If the easiest source is **canonical_metrics** already computed for each signal, **reuse it**. Do not recompute Sharpe with a slightly different convention in the table.

**4) Variant-only BH: where you select the 16 hypotheses**

- When case-study mode is `--case-study liqshock`, BH must include **exactly the 16 liqshock variants** even if other signals were requested.
- **Define:** `liqshock_variants = [k for k in signals_dict if k.startswith("liqshock_")]`; run BH on those only when case-study is on.
- If other signals exist in the run, add one sentence in the memo:  
  *"BH correction is applied to the 16-variant liqshock grid only (case-study mode)."*

**5) Top 10 most valuable pairs: OOS-only by construction**

- Event-rate × median-liquidity score **must use only the OOS (evaluation) window**. Otherwise it looks like peeking.
- **Pattern:** Determine the report's OOS index (whatever reportv2 uses for evaluation—typically the aligned returns index); **slice liquidity and shock series to that index** before computing event rate and medians.
- Define **"extreme shock"** using the same transformation as the signal (recommended: the **pre-negation z-score series** used in the signal).

**8) --strict-fold-factors note (two crisp rules)**

- **If strict mode is not implemented in v1:** always include the **limitation disclosure** line in the memo (e.g. "Factor fitting is not restricted to train window per fold in this run.").
- **If strict mode is implemented and enabled:** include the **positive claim** ("Train-only factor fit per fold applied."). Do not leave it ambiguous.

**10) Memo header: Assumptions bullets**

- In the memo header (or right after it), add a short **Assumptions** bullet list:
  - *"Execution assumed at t+1 bar (as-of lag 1 bar)."*
  - *"No forward-looking liquidity measures used."*
- These two lines are disproportionally powerful in interviews.

---

## E3) Strongly recommended (high ROI, small scope)

**6) --case-study liqshock should lock in grid and headline horizon**

- "Pre-registered" vibe: in case-study mode **print the fixed grid** (N, winsor_p, clip) in the memo.
- **Pick a single headline horizon** (e.g. 1 bar) for the BH p-value and for the executive summary; still show the full horizon table in the appendix. This avoids "Which horizon did you pick to declare victory?"

**7) Keep default report untouched: isolate template rendering**

- **Do not** sprinkle `if args.case_study:` across the whole file.
- **Instead:** collect all normal artifacts/metrics as usual; **if case_study:** call **`render_case_study_memo(...)`** (or similar) with the collected data; **else** use the existing report string builder. Cleaner diff, less risk of breaking the default path.

**9) Tests: make them feasible**

- Integration tests that require a real DB can become a time sink. Prefer:
  - **Unit-test the memo renderer:** pass a small synthetic `signals_dict`, metrics, and table data; **assert** the output includes the required headings and the two table sections (False Discoveries Rejected, Top 10).
  - **Smoke-test argument parsing and branch:** ensure `--case-study liqshock` triggers the case-study renderer (e.g. that the right function is called).
- If you can run reportv2 end-to-end in CI with a fixture DB, do it—but **don't block** on it.

---

## F) Plan doc edits (if not already applied)

If the plan file (e.g. `.cursor/plans/case_study_liqshock_memo_66bdceeb.plan.md`) does not yet include:

1. **§4 "Most valuable":** Add a short subsection under Top 10: "What 'most valuable' means in the memo: 'Valuable' = most economically meaningful + statistically informative under your hypothesis. The Top 10 table should emphasize: stable liquidity (p10), enough volatility/activity, enough shock events to estimate the effect, low missingness. Research capacity + inference quality, not hype coins."

2. **§10 → Concrete implementation slices; §11 → Acceptance criteria:** Replace "Implementation order (suggested)" with the numbered "Concrete implementation slices (order of work)" (spec → signals_xs → reportv2 load/inject/orth → case-study template/tables/note → run.ps1 wrapper → tests; optional strict-fold-factors). Add new section "11. Acceptance criteria" with the command and pytest requirements above.

Apply these manually if the automated plan edits failed due to encoding.
