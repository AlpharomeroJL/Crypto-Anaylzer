# Methods & Limits

This document formalizes the statistical methods used in Crypto-Analyzer's research validation stack and clarifies their assumptions, implementation boundaries, and limitations.

The goal is not to "prove alpha," but to control false discovery, quantify selection bias, and make overfitting visible.

## 1. Research Philosophy

Crypto-Analyzer treats backtesting as a multiple testing problem under dependence.

Markets exhibit:

- Serial dependence
- Cross-sectional correlation
- Heavy tails
- Regime instability
- Non-stationarity

Therefore:

- Naïve Sharpe ratios are inflated.
- Best-in-sample signals are often artifacts.
- Classical IID assumptions are violated.

Our validation stack includes:

- Walk-forward evaluation
- Deflated Sharpe Ratio (DSR)
- Probability of Backtest Overfitting (PBO-style estimate)
- False Discovery Rate control (Benjamini–Hochberg / Benjamini–Yekutieli)
- Stationary bootstrap confidence intervals

Each method addresses a different failure mode.

## 2. Walk-Forward Evaluation

### Purpose

Prevent temporal leakage and training on future information.

### Procedure

- Split data into sequential folds.
- Estimate parameters only on training windows.
- Evaluate strictly on subsequent test windows.
- Aggregate out-of-sample metrics only.

### Limits

- Does not eliminate multiple testing bias.
- Does not guarantee stability under regime shift.
- Requires careful control of feature construction (e.g., rolling OLS must not peek forward).

Walk-forward is necessary but insufficient.

## 3. Deflated Sharpe Ratio (DSR)

### Purpose

Correct Sharpe inflation due to:

- Non-normal returns
- Skewness/kurtosis
- Multiple testing / selection bias

**Canonical reference:** Bailey & López de Prado (2014), *The Deflated Sharpe Ratio* (Deep Research Review of Alpharo…).

### Concept

Given:

- Observed Sharpe ratio *SR*
- Number of trials *N*
- Return skewness and kurtosis

DSR estimates the probability that the observed Sharpe exceeds the maximum expected Sharpe under a null of noise.

Formally, it adjusts the Sharpe using:

- Expected maximum Sharpe under multiple trials
- Finite sample correction
- Higher moment adjustment

### What We Implement

- Use out-of-sample Sharpe only.
- Estimate effective number of trials (see limits below).
- Adjust for skewness and kurtosis.
- Report: Raw Sharpe, expected maximum Sharpe under noise, deflated Sharpe, p-value proxy.

### Limits

- Requires an estimate of the number of independent trials.
- Trial independence is rarely exact in signal research.
- DSR is an approximation; it is not a formal multiple-testing correction like BH/BY.
- Assumes approximate stationarity within folds.
- DSR reduces Sharpe inflation but does not eliminate all selection bias.

## 4. Probability of Backtest Overfitting (PBO)

### Purpose

Quantify how often the "best" in-sample strategy fails out-of-sample.

**Canonical reference:** Bailey et al., *The Probability of Backtest Overfitting* (Deep Research Review of Alpharo…).

### Concept

Using combinatorially symmetric cross-validation (CSCV):

- Partition data into *S* equal blocks.
- Form combinations of train/test splits.
- For each split: rank strategies by in-sample performance; record their out-of-sample rank.
- Compute: **PBO = P(selected strategy performs below median OOS)**.

High PBO → strong overfitting risk.

### What We Implement

- Block-based cross-validation.
- Rank-based OOS performance tracking.
- Empirical PBO estimate.

### Limits

- True CSCV grows combinatorially and can be expensive.
- We may use a computationally tractable approximation.
- Sensitive to block choice.
- Assumes stationarity across blocks.
- Does not correct multiple hypothesis testing by itself.
- PBO measures instability of ranking, not statistical significance.

## 5. Multiple Testing Control

When evaluating many signals simultaneously, the null hypothesis is true for most of them. Without correction, false discoveries dominate.

### 5.1 Benjamini–Hochberg (BH)

**Reference:** Benjamini & Hochberg (1995), *Controlling the False Discovery Rate* (Deep Research Review of Alpharo…).

**Purpose:** Control the expected proportion of false discoveries (FDR).

**Procedure**

- Compute p-values for all signals.
- Sort ascending: *p*₍₁₎ ≤ *p*₍₂₎ ≤ … ≤ *p*₍ₘ₎.
- Find largest *k* such that *p*₍ₖ₎ ≤ (*k*/*m*)α.
- Reject all *p*₍ᵢ₎ ≤ *p*₍ₖ₎.

**Assumption:** Independent or positively dependent tests.

**Limits:** Crypto signals are cross-correlated. BH may be optimistic under arbitrary dependence.

### 5.2 Benjamini–Yekutieli (BY)

**Reference:** Benjamini & Yekutieli (2001) (Deep Research Review of Alpharo…).

**Purpose:** Control FDR under arbitrary dependence.

**Adjustment:** Replace α → α / ∑ᵢ₌₁ᵐ (1/*i*) (more conservative than BH).

**Limits:** Reduced statistical power. May reject very few signals in small samples.

**Interpretation:** BH/BY answer: *Among the signals we promote, what fraction are likely false?* They do not answer: *Will this signal make money?* They control false discoveries, not economic magnitude.

## 6. Stationary Bootstrap

### Purpose

Estimate confidence intervals under serial dependence.

**Reference:** Politis & Romano (1994) (Deep Research Review of Alpharo…).

### Why Not IID Bootstrap?

Financial returns exhibit autocorrelation and volatility clustering. IID resampling destroys structure.

### Stationary Bootstrap

- Sample blocks of random geometric length.
- Preserve local dependence.
- Expected block length chosen via parameter *p*.

**Use cases:** Sharpe confidence intervals, IC confidence intervals, stability of mean returns.

### Limits

- Requires block length selection.
- Assumes weak stationarity.
- Regime shifts violate assumptions.
- Bootstrap CIs may understate tail risk in heavy-tailed crypto returns.
- Bootstrap gives uncertainty bounds, not guarantees.

## 7. Effective Number of Trials (Neff)

Multiple testing requires estimating the number of "independent" tests. Signals are often correlated (e.g., momentum variants, different lookbacks, same factor different universe).

**What we implement:** Eigenvalue-based effective trials $N_{\mathrm{eff}} = (\sum \lambda_i)^2 / \sum \lambda_i^2$ from the correlation matrix of strategy returns. When `--n-trials auto`, reportv2 builds the strategy return matrix from portfolio PnLs, computes Neff, and passes it into DSR; strategies with insufficient valid data may be dropped (alignment policy). When the user passes an explicit integer, that value is used and Neff is not computed.

**Artifact keys (stats_overview.json):** `n_trials_user` (null if auto), `n_trials_eff_eigen` (null if user-specified), `n_trials_used` (always present), `n_trials_eff_inputs_total`, `n_trials_eff_inputs_used`.

**Limits:** No universal definition. Overestimation → too conservative. Underestimation → inflated DSR. We err toward conservatism in promotion thresholds.

## 8. HAC Mean Inference (Newey–West)

**Purpose:** Inference on the mean of a serially correlated series (e.g. portfolio return or IC) using a HAC (heteroskedasticity and autocorrelation consistent) long-run variance estimate.

**What we implement:** Newey–West LRV with Bartlett weights; t-statistic and two-sided p-value (normal approximation). Lag order: `--hac-lags auto` uses a rule (e.g. floor(4*(n/100)^(2/9)) capped by n/3); integer uses that L. **Minimum data:** n ≥ 30; below that, HAC is skipped and we report `hac_skipped_reason` (e.g. "n < 30") with null `t_hac_mean_return` and `p_hac_mean_return`.

**Artifact keys:** `hac_lags_used`, `t_hac_mean_return`, `p_hac_mean_return`, `hac_skipped_reason` (when skipped).

**Limits:** This is inference on the *mean* (or mean IC), not full finite-sample Sharpe inference. Assumes weak dependence and finite variance.

## 9. Reality Check and Romano–Wolf

**Reality Check (RC):** Max-statistic bootstrap test for data snooping. Observed statistic = max over hypotheses (e.g. mean IC); null = same max over bootstrap draws with *shared* resampling indices across hypotheses to preserve dependence. P-value = (1 + count of null max ≥ observed) / (B + 1). Keyed by `family_id`.

**Romano–Wolf (RW):** MaxT stepdown procedure. When enabled (env flag), the repo computes adjusted p-values monotone in stepdown order using the same joint null matrix. **Output contract:** `rw_adjusted_p_values` is *absent* when RW is disabled; when enabled and computed, it is present (non-empty dict hypothesis_id → adjusted p-value). `stats_overview.json` includes `rw_enabled` (bool).

**Artifact keys:** RC summary JSON: `rc_p_value`, `observed_max`, `n_sim`, `hypothesis_ids`, `rc_metric`, `rc_method`, `rc_avg_block_length`; when RW enabled: `rw_adjusted_p_values`, `rw_alpha`, bootstrap params.

**Limits:** RC and RW assume the bootstrap null is appropriate; regime breaks can distort calibration.

## 10. CSCV PBO (Combinatorially Symmetric Cross-Validation)

**Purpose:** Canonical PBO = P(λ < 0) where λ = logit(rank_OOS), i.e. probability the in-sample selected strategy performs below median OOS.

**What we implement:** Data split into S blocks (S even); train/test = half each. For each split, rank strategies by in-sample metric, compute OOS rank of the winner, then λ. PBO = fraction of splits with λ < 0. If choose(S, S/2) exceeds `max_splits`, we random-sample splits with a seed. Midrank used for ties. **Minimum data:** T ≥ S×min_block_len (e.g. 4) and J ≥ 2; otherwise CSCV is skipped with `pbo_cscv_skipped_reason` (e.g. "T < S*4", "S must be even").

**Artifact keys:** `pbo_cscv`, `pbo_cscv_blocks`, `pbo_cscv_total_splits`, `pbo_cscv_splits_used`, `pbo_metric`; when skipped: `pbo_cscv_skipped_reason`.

**Limits:** Block stationarity; PBO measures ranking instability, not significance.

## 11. Structural Break Diagnostics

**What we implement:** (1) **CUSUM mean-shift:** HAC-calibrated CUSUM statistic; `calibration_method`: "HAC". (2) **Sup-Chow single-break scan:** asymptotic sup-Wald over candidate break dates; `calibration_method`: "asymptotic". Both return `stat`, `p_value`, `break_suspected`, `estimated_break_index`, `estimated_break_date` (UTC-normalized to naive, format "%Y-%m-%dT%H:%M:%S"). When skipped (e.g. n below minimum): `skipped_reason` set, `break_suspected` false, stat/p/date null. Min obs: CUSUM e.g. 20; scan 100.

**Artifacts:** `break_diagnostics.json` — top-level key `series`; per series, list of test entries (cusum, sup_chow) with the fields above. `stats_overview.json`: `break_diagnostics_written` (bool), `break_diagnostics_skipped_reason` (when no series written).

**Limits:** Single-break scan; regime instability may require more than one break.

## 12. Capacity Curve and Execution Evidence

**What we implement:** Capacity curve = Sharpe (and optional audit columns) vs notional multiplier. **Impact model:** When participation-based impact is used (`use_participation_impact=True`): participation proxy = min(max_participation_pct, multiplier × mean(turnover) × 100); impact_bps from participation (linear in participation, capped). Otherwise fallback: power-law impact_k × m^impact_alpha. Net returns = gross − (fee + slippage + spread + impact) applied to turnover. **CSV contract:** First two columns are `notional_multiplier`, `sharpe_annual` (required, order fixed); extra columns (e.g. mean_ret_annual, vol_annual, avg_turnover, est_cost_bps, impact_bps, spread_bps) are additive only. We do *not* force monotonicity: if Sharpe increases with multiplier, we set `non_monotone_capacity_curve_observed` in stats_overview.

**Artifact keys:** `stats_overview.json`: `capacity_curve_written`, `non_monotone_capacity_curve_observed`. Capacity curve CSV; `execution_evidence.json` with `cost_config` (participation params when used) and `capacity_curve_path`.

**Limits:** Participation is a proxy (e.g. turnover vs ADV); execution evidence is for audit, not live execution.

## 13. Artifacts / Audit (Stats Stack Keys)

Single source of truth for JSON/CSV keys introduced by upgrades #1–#6:

- **stats_overview.json:** `n_trials_user`, `n_trials_eff_eigen`, `n_trials_used`, `n_trials_eff_inputs_total`, `n_trials_eff_inputs_used`; `hac_lags_used`, `hac_skipped_reason`, `t_hac_mean_return`, `p_hac_mean_return`; `pbo_cscv`, `pbo_cscv_blocks`, `pbo_cscv_total_splits`, `pbo_cscv_splits_used`, `pbo_metric`, `pbo_cscv_skipped_reason`; `rw_enabled`; `break_diagnostics_written`, `break_diagnostics_skipped_reason`; `capacity_curve_written`, `non_monotone_capacity_curve_observed`.
- **break_diagnostics.json:** `series` → { series_name → [ { test_name, stat, p_value, break_suspected, estimated_break_index, estimated_break_date, calibration_method, skipped_reason? } ] }.
- **reality_check_summary_*.json:** `rw_adjusted_p_values` (when RW enabled), plus existing RC keys.
- **execution_evidence_*.json:** `cost_config` (must match model used in capacity_curve), `capacity_curve_path`.

Skip behavior: when a component is skipped, the corresponding reason key is set (e.g. `hac_skipped_reason`, `pbo_cscv_skipped_reason`); statistic keys are null or omitted. See [Stats stack acceptance](spec/stats_stack_upgrade_acceptance.md).

## 14. Null Suite (Placebo Tests)

Every research report can include:

- Randomized signals
- Lag-shuffled signals
- Sign-flipped signals

If placebo signals pass validation gates, thresholds are tightened. This acts as an empirical Reality Check proxy (White, 2000) (Deep Research Review of Alpharo…).

## 15. What This Stack Does NOT Guarantee

- Future profitability
- Stability across structural breaks
- Liquidity realizability
- Execution feasibility
- Immunity to regime change
- Protection against data errors

It *reduces*: selection bias, false discoveries, Sharpe inflation, backtest overfitting visibility. It does not eliminate uncertainty.

## 16. Implementation Boundaries

| Method              | Fully Implemented | Approximate              | Known Limits        |
|---------------------|-------------------|--------------------------|---------------------|
| Walk-forward        | Yes               | —                        | Regime sensitivity  |
| DSR + Neff          | Yes               | Trial count (eigen)      | Dependence assumption |
| PBO proxy + CSCV    | Yes               | Block/split sampling     | Block sensitivity   |
| BH / BY             | Yes               | —                        | Independence / conservative |
| Stationary bootstrap| Yes               | Block parameter choice   | Stationarity        |
| Reality Check       | Yes               | —                        | Null validity       |
| Romano–Wolf         | Yes (opt-in)      | —                        | Same as RC          |
| HAC mean inference  | Yes               | n ≥ 30                   | Mean only           |
| Break diagnostics  | Yes               | CUSUM / sup-Chow         | Single break        |
| Capacity curve      | Yes               | Participation or power-law| Liquidity proxy     |

## 17. Interpretation Hierarchy

Signals are promoted only if:

- Positive OOS Sharpe
- DSR exceeds threshold
- Survive BH/BY at chosen FDR
- Acceptable PBO
- Stable under bootstrap CIs
- Null suite does not pass

All conditions must hold.

## 18. Research Integrity Statement

Crypto-Analyzer is a research validation engine. It is not a trading system, an execution engine, or a guarantee of profit.

All outputs are conditional on: data quality, model assumptions, market stability.

## 19. References

- Bailey & López de Prado (2014), *The Deflated Sharpe Ratio* (Deep Research Review of Alpharo…).
- Bailey et al., *The Probability of Backtest Overfitting* (Deep Research Review of Alpharo…).
- Benjamini & Hochberg (1995), FDR control (Deep Research Review of Alpharo…).
- Benjamini & Yekutieli (2001), FDR under dependence (Deep Research Review of Alpharo…).
- Politis & Romano (1994), Stationary bootstrap (Deep Research Review of Alpharo…).
- White (2000), Reality Check (Deep Research Review of Alpharo…).
