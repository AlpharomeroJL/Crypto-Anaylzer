# Appendix: Methods & Limits (DSR, PBO, BH/BY, Bootstrap, Reality Check)

This document matches the **exact implementations** in this repo for DSR, BH/BY, PBO proxy, and the stationary/block bootstrap used for Reality Check. It expands equations, derivation steps, and asymptotics.

## Notation

Let returns (or PnL increments) be a time series \( \{r_t\}_{t=1}^{n} \), with sample mean

$$
\bar{r} = \frac{1}{n} \sum_{t=1}^{n} r_t
$$

and sample standard deviation (ddof \( = 1 \))

$$
s = \sqrt{ \frac{1}{n-1} \sum_{t=1}^{n} (r_t - \bar{r})^2 }.
$$

The repo's raw Sharpe is computed as

$$
\widehat{SR} = \frac{\bar{r}}{s},
$$

using ddof \( = 1 \) for \( s \) (see `multiple_testing`).

---

## A. Deflated Sharpe Ratio (DSR)

### A.1 Implementation-aligned definition

This repo computes:

1. **Raw Sharpe:** \( \widehat{SR} = \bar{r} / s \).

2. **A variance estimate for \( \widehat{SR} \)** under i.i.d.-style approximations including skewness and excess kurtosis: sample skewness \( \hat{\gamma} \) and excess kurtosis \( \hat{\kappa} \) are taken from the series (pandas `skew()` and `kurtosis()`; the latter is excess kurtosis). The code uses:

$$
\widehat{\operatorname{Var}}(\widehat{SR}) = \frac{ 1 + \frac{1}{2} \widehat{SR}^2 - \hat{\gamma} \, \widehat{SR} + \frac{1}{4} \hat{\kappa} \, \widehat{SR}^2 }{ n }
$$

(then floored at \( 10^{-12} \)). This is exactly what's implemented in `multiple_testing`.

Define \( \hat{\sigma}_{SR} = \sqrt{ \widehat{\operatorname{Var}}(\widehat{SR}) } \).

3. **A multiple-testing "winner's curse" correction** via an approximation to the expected maximum Sharpe under the null across \( N \) trials (where \( N = \max(\texttt{n\_trials\_estimate}, 1) \)):

$$
\widehat{E}[\max SR_{\mathrm{null}}] \approx \hat{\sigma}_{SR} \sqrt{2 \ln N}
$$

(see `multiple_testing`).

4. **The repo's returned deflated score:**

$$
DSR_{\mathrm{repo}} = \frac{ \widehat{SR} - \widehat{E}[\max SR_{\mathrm{null}}] }{ \hat{\sigma}_{SR} } = \frac{ \widehat{SR} }{ \hat{\sigma}_{SR} } - \sqrt{2 \ln N},
$$

matching `deflated_sr = (raw_sr - e_max_sr) / std_sr` in `multiple_testing`.

**Important:** This returned value is a standardized exceedance against an extreme-value null approximation, not the same scalar as "Sharpe minus penalty." The function returns both `raw_sr` and `deflated_sr` (see `multiple_testing`).

### A.2 Derivation steps: why \( \sqrt{2 \ln N} \) appears

Let \( Z_1, \ldots, Z_N \) be i.i.d. \( N(0, 1) \). A standard bound for the maximum is:

**Tail bound:** \( P(\max_i Z_i \leq x) = \Phi(x)^N \).

For large \( x \), \( 1 - \Phi(x) \approx \frac{1}{x} \phi(x) \), so setting \( P(\max Z_i \leq x) \approx \exp(-N(1 - \Phi(x))) \) suggests the typical maximum solves \( N(1 - \Phi(x)) \approx 1 \), yielding \( x \approx \sqrt{2 \ln N} \) as the first-order term.

More formally, extreme-value theory gives:

$$
\max_i Z_i = \sqrt{2 \ln N} - \frac{ \ln\ln N + \ln(4\pi) }{ 2\sqrt{2\ln N} } + o_p\!\left( \frac{1}{\sqrt{\ln N}} \right),
$$

so \( E[\max_i Z_i] = \sqrt{2 \ln N} + o(\sqrt{\ln N}) \). The repo uses the leading term only (no \( \ln\ln N \) refinement); see `multiple_testing`.

If under the null each trial's Sharpe estimator is approximately normal, \( \widehat{SR}_j \approx N(0, \sigma_{SR}^2) \), then \( \max_j \widehat{SR}_j \approx \sigma_{SR} \max_j Z_j \), hence:

$$
E[\max_j \widehat{SR}_j] \approx \sigma_{SR} \sqrt{2 \ln N}.
$$

### A.3 Asymptotics and limits

**(i) Asymptotic size of the "penalty."** The null expected maximum scales as \( \widehat{E}[\max SR_{\mathrm{null}}] = \Theta(\hat{\sigma}_{SR} \sqrt{\ln N}) \). Since (under i.i.d. with finite moments) \( \hat{\sigma}_{SR} = \Theta(n^{-1/2}) \), the penalty is \( \Theta(\sqrt{\ln N / n}) \). So increasing \( N \) at fixed \( n \) raises the bar slowly (logarithmically), while increasing \( n \) shrinks the bar at \( n^{-1/2} \).

**(ii) Dependence / non-i.i.d. returns.** The variance formula and the normal-max approximation assume rough i.i.d.-style behavior (see `multiple_testing`). Autocorrelation, volatility clustering, regime shifts, and heavy tails can make \( \widehat{\operatorname{Var}}(\widehat{SR}) \) materially wrong, miscalibrating \( DSR_{\mathrm{repo}} \).

**(iii) "Trials" \( N \) is user-provided.** The code treats `n_trials_estimate` as a stand-in for the effective number of tested variants (see `multiple_testing`). If the true search space is larger, DSR is optimistic; if smaller, overly conservative.

---

## B. Benjamini–Hochberg (BH) and Benjamini–Yekutieli (BY)

### B.1 Implementation-aligned algorithm

Given \( m \) p-values \( p_1, \ldots, p_m \), this repo:

1. Drops NaNs, sorts ascending to \( p_{(1)} \leq \cdots \leq p_{(m)} \) (see `multiple_testing_adjuster`).
2. Computes adjusted values:
   - **BH:** \( \tilde{p}_{(i)} = \min\!\left( 1, \; p_{(i)} \frac{m}{i} \right) \) (see `multiple_testing_adjuster`).
   - **BY:** \( c_m = \sum_{j=1}^{m} \frac{1}{j} \), \( \tilde{p}_{(i)} = \min\!\left( 1, \; p_{(i)} \frac{m \, c_m}{i} \right) \) (see `multiple_testing_adjuster`).
3. Enforces monotonicity in the sorted order (non-decreasing adjusted p-values): \( \tilde{p}_{(i)} \leftarrow \max(\tilde{p}_{(i)}, \tilde{p}_{(i-1)}) \) (see `multiple_testing_adjuster`).
4. Maps back to original indices and declares discoveries where \( \texttt{adj} \leq q \) (see `multiple_testing_adjuster`).

### B.2 Derivation: BY's harmonic factor and asymptotics

BY modifies BH to remain valid under arbitrary dependence by inflating the threshold by \( c_m \). The harmonic number satisfies:

$$
c_m = H_m = \sum_{j=1}^{m} \frac{1}{j} = \ln m + \gamma + \frac{1}{2m} + o\!\left( \frac{1}{m} \right),
$$

so BY is more conservative by a factor asymptotically \( \ln m \). This is why the repo's BY adjusted p-values are guaranteed \( \geq \) BH adjusted p-values (also asserted in tests; see `test_multiple_testing_adjuster`).

---

## C. PBO (Probability of Backtest Overfitting) — repo "proxy"

### C.1 What the repo computes

The repo implements a **walk-forward PBO proxy**:

- **Input:** A DataFrame with split identifiers and train/test metrics (e.g. `train_sharpe`, `test_sharpe`); see `multiple_testing`.
- It defines: \( n_{\mathrm{splits}} \) = number of unique splits (must be \( \geq 2 \)); \( m = \mathrm{median}(\{\text{test metric values}\}) \); see `multiple_testing`.
- It counts how often the (assumed) "selected" strategy underperforms that median:

$$
\text{underperform} = \sum_{k=1}^{K} \mathbf{1}\{ T_k < m \},
$$

where \( T_k \) is the test metric in row \( k \), and \( K = \texttt{len(results\_df)} \); see `multiple_testing`.

- It returns:

$$
\widehat{PBO}_{\mathrm{proxy}} = \frac{ \text{underperform} }{ K }
$$

(see `multiple_testing`).

The docstring states the intended interpretation: "fraction of splits where the strategy (best in train) underperformed median test metric" (see `multiple_testing`).

### C.2 Limits (important)

This is **not** full CSCV PBO (as in López de Prado). It does **not**:

- enumerate many candidate models per split and select the best in-sample within each fold,
- compute the rank of out-of-sample performance among candidates,
- transform ranks into \( \lambda = \log(p/(1-p)) \) and take \( P(\lambda < 0) \).

Instead, it assumes each row corresponds to "the chosen strategy for that split" (see `multiple_testing`) and then compares its test metric to the median across splits. **Treat this as a screening heuristic, not a calibrated probability of overfitting.**

---

## D. Bootstrap for dependent time series

This repo includes both **fixed block bootstrap** and **stationary bootstrap (Politis–Romano)**.

### D.1 Stationary bootstrap indices (exact implementation)

The stationary bootstrap draws blocks of random (geometric) length with mean \( \ell \) (`avg_block_length`) and concatenates them until length \( n \). At each block start, a random starting index is sampled uniformly from \( \{0, \ldots, n-1\} \), and the block proceeds forward with wrap-around (mod \( n \)); see `statistics`.

**Parameter mapping:** \( p = 1/\ell \), \( L \sim \mathrm{Geometric}(p) \Rightarrow E[L] = \ell \). This is exactly described and implemented in `statistics`.

### D.2 Fixed block bootstrap indices (exact implementation for RC)

For fixed block bootstrap in the RC module, indices are built by repeatedly sampling a start \( \in \{0, \ldots, n - b\} \) and appending the block \( [\texttt{start}, \texttt{start} + b) \) until length \( n \); see `reality_check`.

### D.3 Asymptotic notes (consistency conditions)

For dependent stationary processes (mixing conditions), block bootstraps are consistent for many smooth functionals if block length \( b = b_n \) satisfies:

$$
b_n \to \infty \quad \text{and} \quad \frac{b_n}{n} \to 0 \quad (n \to \infty).
$$

Stationary bootstrap uses random block lengths with mean \( \ell_n \) playing the role of \( b_n \); similar conditions apply: \( \ell_n \to \infty \), \( \ell_n / n \to 0 \).

**Practical implication:** If \( \ell \) is too small, dependence is broken (CI too tight); if too large, you effectively resample whole regimes (variance inflated, fewer effective resamples).

---

## E. Reality Check (RC) for data snooping (dependence-aware)

### E.1 Spec and algorithm

The repo's Phase 3 Slice 4 spec defines:

- **Observed statistic:** \( T_{\mathrm{obs}} = \max_{h \in \mathcal{H}} \hat{\theta}_h \), where \( \hat{\theta}_h \) is a per-hypothesis statistic (default mean IC); see `phase3_reality_check_slice4_ali…`.
- **Null generation:** For each bootstrap draw \( b = 1, \ldots, B \), produce a vector \( \hat{\theta}_h^{*(b)} \) using the **same resampling indices across hypotheses** to preserve dependence:

$$
T^{*(b)} = \max_{h \in \mathcal{H}} \hat{\theta}_h^{*(b)};
$$

see `phase3_reality_check_slice4_ali…`.
- **P-value:**

$$
\hat{p}_{\mathrm{RC}} = \frac{ 1 + \#\{ b : T^{*(b)} \geq T_{\mathrm{obs}} \} }{ B + 1 }
$$

(see `phase3_reality_check_slice4_ali…` and implemented in `reality_check`).

### E.2 Implementation details (null generator)

The null generator builder intersects indices so every hypothesis series is aligned on a common index set (see `reality_check`). For bootstrap draw \( b \), it uses a per-draw seed \( \texttt{seed\_b} = \texttt{seed} + b \) (see `reality_check`) and computes (for mean-IC metric) the resampled statistic as a simple mean:

$$
\hat{\theta}_h^{*(b)} = \mathrm{nanmean}(\{ x_{h, t_j} \}_{j=1}^{n}).
$$

See `reality_check`.

### E.3 Romano–Wolf

Romano–Wolf stepdown is explicitly **stubbed / not implemented** (raises if enabled); see `reality_check`. The spec says Slice 4 implements RC only; see `phase3_reality_check_slice4_ali…`.

---

## F. "Methods & Limits" summary (what to claim safely)

- **DSR** here is a screening statistic using an i.i.d.-style Sharpe variance approximation with skew/excess kurtosis and a leading-order extreme-value correction \( \sqrt{2 \ln N} \) (see `multiple_testing`). It is not a full, formally calibrated multiple-testing p-value.
- **BH/BY** are standard FDR adjustments; BY's harmonic inflation \( c_m \) makes it valid under arbitrary dependence and asymptotically costs a \( \ln m \) factor (see `multiple_testing_adjuster`).
- **PBO proxy** is a heuristic "median underperformance rate" across walk-forward splits, not CSCV PBO (see `multiple_testing`).
- **Bootstrap** uses fixed or stationary blocks; stationary bootstrap uses geometric block lengths with mean \( \ell \) and wrap-around (see `statistics`).
- **Reality Check** is implemented as a max-statistic bootstrap test with dependence preserved by sharing resampling indices across hypotheses, and p-value \( (1 + \#\{ T^* \geq T \}) / (B + 1) \); see `reality_check`.
