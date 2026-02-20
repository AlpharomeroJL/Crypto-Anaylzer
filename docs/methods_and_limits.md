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

## 7. Effective Number of Trials

Multiple testing requires estimating the number of "independent" tests. Signals are often correlated (e.g., momentum variants, different lookbacks, same factor different universe).

We estimate effective trials via:

- Correlation matrix eigenvalue shrinkage, or
- Conservative full count assumption.

**Limits:** No universal definition. Overestimation → too conservative. Underestimation → inflated DSR. We err toward conservatism in promotion thresholds.

## 8. Null Suite (Placebo Tests)

Every research report includes:

- Randomized signals
- Lag-shuffled signals
- Sign-flipped signals

If placebo signals pass validation gates, thresholds are tightened. This acts as an empirical Reality Check proxy (White, 2000) (Deep Research Review of Alpharo…).

## 9. What This Stack Does NOT Guarantee

- Future profitability
- Stability across structural breaks
- Liquidity realizability
- Execution feasibility
- Immunity to regime change
- Protection against data errors

It *reduces*: selection bias, false discoveries, Sharpe inflation, backtest overfitting visibility. It does not eliminate uncertainty.

## 10. Implementation Boundaries

| Method              | Fully Implemented | Approximate              | Known Limits        |
|---------------------|-------------------|--------------------------|---------------------|
| Walk-forward        | Yes               | —                        | Regime sensitivity  |
| DSR                 | Yes               | Trial count estimate     | Dependence assumption |
| PBO                 | Approximate CSCV  | Yes                      | Block sensitivity   |
| BH                  | Yes               | —                        | Independence assumption |
| BY                  | Yes               | —                        | Conservative        |
| Stationary bootstrap| Yes               | Block parameter choice   | Stationarity        |

## 11. Interpretation Hierarchy

Signals are promoted only if:

- Positive OOS Sharpe
- DSR exceeds threshold
- Survive BH/BY at chosen FDR
- Acceptable PBO
- Stable under bootstrap CIs
- Null suite does not pass

All conditions must hold.

## 12. Research Integrity Statement

Crypto-Analyzer is a research validation engine. It is not a trading system, an execution engine, or a guarantee of profit.

All outputs are conditional on: data quality, model assumptions, market stability.

## 13. References

- Bailey & López de Prado (2014), *The Deflated Sharpe Ratio* (Deep Research Review of Alpharo…).
- Bailey et al., *The Probability of Backtest Overfitting* (Deep Research Review of Alpharo…).
- Benjamini & Hochberg (1995), FDR control (Deep Research Review of Alpharo…).
- Benjamini & Yekutieli (2001), FDR under dependence (Deep Research Review of Alpharo…).
- Politis & Romano (1994), Stationary bootstrap (Deep Research Review of Alpharo…).
- White (2000), Reality Check (Deep Research Review of Alpharo…).
