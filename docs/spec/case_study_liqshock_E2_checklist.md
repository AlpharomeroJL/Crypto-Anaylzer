# Case Study Liqshock — E2 Must-Fix Checklist

Source: [case_study_liqshock_proposed_diffs.md](case_study_liqshock_proposed_diffs.md) §E2. Check each before moving on.

---

## Scope decision (Phase 0)

- [ ] **--strict-fold-factors in v1?** → **NO** (not implemented in repo). **v1 = disclosure line only.** Always include limitation text: *"Factor fitting is not restricted to train window per fold in this run."* Do not implement --strict-fold-factors in v1; if implemented later, add positive claim and switch.

---

## E2 Must-fix items

- [ ] **1) load_bars() + pair_id match returns_df.columns**  
  Only keep bars whose pair_id is in returns_df.columns (or pivot then intersect). In case-study mode log: `"returns columns: X, bars columns matched: Y (Z%)"`.

- [ ] **2) Liquidity log floor**  
  In signal: `L = liquidity_panel.clip(lower=1.0)` then `np.log(L)`. Roll_vol: `replace(0, np.nan)` and/or `clip(lower=eps)` before use.

- [ ] **3) Raw Sharpe in BH table**  
  Same portfolio config as run (e.g. --portfolio advanced), OOS. Reuse canonical_metrics; do not recompute with different convention.

- [ ] **4) Variant-only BH**  
  `liqshock_variants = [k for k in signals_dict if k.startswith("liqshock_")]`; BH on those only when case-study. If other signals present, add: *"BH correction is applied to the 16-variant liqshock grid only (case-study mode)."*

- [ ] **5) Top 10 OOS-only**  
  Event-rate × median-liquidity use OOS index only. Slice liquidity/shock to report evaluation index. Define extreme shock from same pre-negation z-score as signal.

- [ ] **8) strict-fold-factors note**  
  v1: always include **limitation disclosure** (factor fitting not restricted to train per fold). If/when strict mode exists and is enabled: use **positive claim** instead.

- [ ] **10) Assumptions in memo header**  
  Bullets: *"Execution assumed at t+1 bar (as-of lag 1 bar)."* *"No forward-looking liquidity measures used."*

---

*Do not change the plan during execution unless something truly blocks.*
