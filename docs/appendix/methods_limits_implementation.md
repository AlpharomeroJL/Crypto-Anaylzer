# Appendix: Methods & Limits (DSR, PBO, BH/BY, Bootstrap, Reality Check)

This document matches the **exact implementations** in this repo for DSR, BH/BY, PBO proxy, and the stationary/block bootstrap used for Reality Check. It expands equations, derivation steps, and asymptotics.

## Notation

Let returns (or PnL increments) be a time series $\{r_t\}_{t=1}^{n}$, with sample mean

$$\bar{r} = \frac{1}{n} \sum_{t=1}^{n} r_t$$

and sample standard deviation (ddof $= 1$)

$$s = \sqrt{ \frac{1}{n-1} \sum_{t=1}^{n} (r_t - \bar{r})^2 }.$$

The repo's raw Sharpe is computed as

$$\widehat{SR} = \frac{\bar{r}}{s},$$

using ddof $= 1$ for $s$ (see `multiple_testing`).

---

## A. Deflated Sharpe Ratio (DSR)

### A.1 Implementation-aligned definition

This repo computes:

1. **Raw Sharpe:** $\widehat{SR} = \bar{r} / s$.

2. **A variance estimate for $\widehat{SR}$** under i.i.d.-style approximations including skewness and excess kurtosis: sample skewness $\hat{\gamma}$ and excess kurtosis $\hat{\kappa}$ are taken from the series (pandas `skew()` and `kurtosis()`; the latter is excess kurtosis). The code uses:

$$\widehat{\text{Var}}(\widehat{SR}) = \frac{ 1 + \frac{1}{2} \widehat{SR}^2 - \hat{\gamma} \, \widehat{SR} + \frac{1}{4} \hat{\kappa} \, \widehat{SR}^2 }{ n }$$

(then floored at $10^{-12}$). This is exactly what's implemented in `multiple_testing`.

Define $\hat{\sigma}_{SR} = \sqrt{ \widehat{\text{Var}}(\widehat{SR}) }$.

3. **A multiple-testing "winner's curse" correction** via an approximation to the expected maximum Sharpe under the null across $N$ trials (where $N = \max(\mathrm{n\_trials\_estimate}, 1)$):

$$\widehat{E}[\max SR_{\mathrm{null}}] \approx \hat{\sigma}_{SR} \sqrt{2 \ln N}$$

(see `multiple_testing`).

4. **The repo's returned deflated score:**

$$DSR_{\mathrm{repo}} = \frac{ \widehat{SR} - \widehat{E}[\max SR_{\mathrm{null}}] }{ \hat{\sigma}_{SR} } = \frac{ \widehat{SR} }{ \hat{\sigma}_{SR} } - \sqrt{2 \ln N},$$

matching `deflated_sr = (raw_sr - e_max_sr) / std_sr` in `multiple_testing`.

**Important:** This returned value is a standardized exceedance against an extreme-value null approximation, not the same scalar as "Sharpe minus penalty." The function returns both `raw_sr` and `deflated_sr` (see `multiple_testing`).

### A.2 Derivation steps: why $\sqrt{2 \ln N}$ appears

Let $Z_1, \ldots, Z_N$ be i.i.d. $N(0, 1)$. A standard bound for the maximum is:

**Tail bound:** $P(\max_i Z_i \leq x) = \Phi(x)^N$.

For large $x$, $1 - \Phi(x) \approx \frac{1}{x} \phi(x)$, so setting $P(\max Z_i \leq x) \approx \exp(-N(1 - \Phi(x)))$ suggests the typical maximum solves $N(1 - \Phi(x)) \approx 1$, yielding $x \approx \sqrt{2 \ln N}$ as the first-order term.

More formally, extreme-value theory gives:

$$\max_i Z_i = \sqrt{2 \ln N} - \frac{ \ln\ln N + \ln(4\pi) }{ 2\sqrt{2\ln N} } + o_p\!\left( \frac{1}{\sqrt{\ln N}} \right),$$

so $E[\max_i Z_i] = \sqrt{2 \ln N} + o(\sqrt{\ln N})$. The repo uses the leading term only (no $\ln\ln N$ refinement); see `multiple_testing`.

If under the null each trial's Sharpe estimator is approximately normal, $\widehat{SR}_j \approx N(0, \sigma_{SR}^2)$, then $\max_j \widehat{SR}_j \approx \sigma_{SR} \max_j Z_j$, hence:

$$E[\max_j \widehat{SR}_j] \approx \sigma_{SR} \sqrt{2 \ln N}.$$

### A.3 Asymptotics and limits

**(i) Asymptotic size of the "penalty."** The null expected maximum scales as $\widehat{E}[\max SR_{\mathrm{null}}] = \Theta(\hat{\sigma}_{SR} \sqrt{\ln N})$. Since (under i.i.d. with finite moments) $\hat{\sigma}_{SR} = \Theta(n^{-1/2})$, the penalty is $\Theta(\sqrt{\ln N / n})$. So increasing $N$ at fixed $n$ raises the bar slowly (logarithmically), while increasing $n$ shrinks the bar at $n^{-1/2}$.

**(ii) Dependence / non-i.i.d. returns.** The variance formula and the normal-max approximation assume rough i.i.d.-style behavior (see `multiple_testing`). Autocorrelation, volatility clustering, regime shifts, and heavy tails can make $\widehat{\text{Var}}(\widehat{SR})$ materially wrong, miscalibrating $DSR_{\mathrm{repo}}$.

**(iii) "Trials" $N$ is user-provided.** The code treats `n_trials_estimate` as a stand-in for the effective number of tested variants (see `multiple_testing`). If the true search space is larger, DSR is optimistic; if smaller, overly conservative.

---

## B. Benjamini–Hochberg (BH) and Benjamini–Yekutieli (BY)

### B.1 Implementation-aligned algorithm

Given $m$ p-values $p_1, \ldots, p_m$, this repo:

1. Drops NaNs, sorts ascending to $p_{(1)} \leq \cdots \leq p_{(m)}$ (see `multiple_testing_adjuster`).
2. Computes adjusted values:
   - **BH:** $\tilde{p}_{(i)} = \min\!\left(1,\; p_{(i)} \frac{m}{i}\right)$ (see `multiple_testing_adjuster`).
   - **BY:** Harmonic sum $c_m = \sum_{j=1}^{m} \frac{1}{j}$; then $\tilde{p}_{(i)} = \min\!\left(1,\; p_{(i)} \frac{m\,c_m}{i}\right)$ (see `multiple_testing_adjuster`).
3. Enforces monotonicity in the sorted order (non-decreasing adjusted p-values): $\tilde{p}_{(i)} \leftarrow \max(\tilde{p}_{(i)}, \tilde{p}_{(i-1)})$ (see `multiple_testing_adjuster`).
4. Maps back to original indices and declares discoveries where $\mathrm{adj} \leq q$ (see `multiple_testing_adjuster`).

### B.2 Derivation: BY's harmonic factor and asymptotics

BY modifies BH to remain valid under arbitrary dependence by inflating the threshold by $c_m$. The harmonic number satisfies:

$$c_m = H_m = \sum_{j=1}^{m} \frac{1}{j} = \ln m + \gamma + \frac{1}{2m} + o\!\left( \frac{1}{m} \right),$$

so BY is more conservative by a factor asymptotically $\ln m$. This is why the repo's BY adjusted p-values are guaranteed $\geq$ BH adjusted p-values (also asserted in tests; see `test_multiple_testing_adjuster`).

---

## C. PBO (Probability of Backtest Overfitting) — repo "proxy"

### C.1 What the repo computes

The repo implements a **walk-forward PBO proxy**:

- **Input:** A DataFrame with split identifiers and train/test metrics (e.g. `train_sharpe`, `test_sharpe`); see `multiple_testing`.
- It defines: $n_{\mathrm{splits}}$ = number of unique splits (must be $\geq 2$); $m = \mathrm{median}(\{\text{test metric values}\})$; see `multiple_testing`.
- It counts how often the (assumed) "selected" strategy underperforms that median:

$$\text{underperform} = \sum_{k=1}^{K} \mathbf{1}\{ T_k < m \},$$

where $T_k$ is the test metric in row $k$, and $K = \mathrm{len}(\mathrm{results\_df})$; see `multiple_testing`.

- It returns:

$$\widehat{PBO}_{\mathrm{proxy}} = \frac{ \text{underperform} }{ K }$$

(see `multiple_testing`).

The docstring states the intended interpretation: "fraction of splits where the strategy (best in train) underperformed median test metric" (see `multiple_testing`).

### C.2 Limits (important)

This is **not** full CSCV PBO (as in López de Prado). It does **not**:

- enumerate many candidate models per split and select the best in-sample within each fold,
- compute the rank of out-of-sample performance among candidates,
- transform ranks into $\lambda = \log(p/(1-p))$ and take $P(\lambda < 0)$.

Instead, it assumes each row corresponds to "the chosen strategy for that split" (see `multiple_testing`) and then compares its test metric to the median across splits. **Treat this as a screening heuristic, not a calibrated probability of overfitting.**

---

## D. Bootstrap for dependent time series

This repo includes both **fixed block bootstrap** and **stationary bootstrap (Politis–Romano)**.

### D.1 Stationary bootstrap indices (exact implementation)

The stationary bootstrap draws blocks of random (geometric) length with mean $\ell$ (`avg_block_length`) and concatenates them until length $n$. At each block start, a random starting index is sampled uniformly from $\{0, \ldots, n-1\}$, and the block proceeds forward with wrap-around (mod $n$); see `statistics`.

**Parameter mapping:** $p = 1/\ell$, $L \sim \mathrm{Geometric}(p) \Rightarrow E[L] = \ell$. This is exactly described and implemented in `statistics`.

### D.2 Fixed block bootstrap indices (exact implementation for RC)

For fixed block bootstrap in the RC module, indices are built by repeatedly sampling a start $\in \{0, \ldots, n - b\}$ and appending the block $[\mathrm{start}, \mathrm{start} + b)$ until length $n$; see `reality_check`.

### D.3 Asymptotic notes (consistency conditions)

For dependent stationary processes (mixing conditions), block bootstraps are consistent for many smooth functionals if block length $b = b_n$ satisfies:

$$b_n \to \infty \quad \text{and} \quad \frac{b_n}{n} \to 0 \quad (n \to \infty).$$

Stationary bootstrap uses random block lengths with mean $\ell_n$ playing the role of $b_n$; similar conditions apply: $\ell_n \to \infty$, $\ell_n / n \to 0$.

**Practical implication:** If $\ell$ is too small, dependence is broken (CI too tight); if too large, you effectively resample whole regimes (variance inflated, fewer effective resamples).

---

## E. Reality Check (RC) for data snooping (dependence-aware)

### E.1 Spec and algorithm

The repo's Phase 3 Slice 4 spec defines:

- **Observed statistic:** $T_{\mathrm{obs}} = \max_{h \in \mathcal{H}} \hat{\theta}_h$, where $\hat{\theta}_h$ is a per-hypothesis statistic (default mean IC); see `phase3_reality_check_slice4_ali…`.
- **Null generation:** For each bootstrap draw $b = 1, \ldots, B$, produce a vector $\hat{\theta}_h^{*(b)}$ using the **same resampling indices across hypotheses** to preserve dependence:

$$T^{*(b)} = \max_{h \in \mathcal{H}} \hat{\theta}_h^{*(b)};$$

see `phase3_reality_check_slice4_ali…`.
- **P-value:**

$$\hat{p}_{\mathrm{RC}} = \frac{ 1 + \bigl\lvert \lbrace b : T^{*(b)} \geq T_{\mathrm{obs}} \rbrace \bigr\rvert }{ B + 1 }$$

(see `phase3_reality_check_slice4_ali…` and implemented in `reality_check`).

### E.2 Implementation details (null generator)

The null generator builder intersects indices so every hypothesis series is aligned on a common index set (see `reality_check`). For bootstrap draw $b$, it uses a per-draw seed $\mathrm{seed\_b} = \mathrm{seed} + b$ (see `reality_check`) and computes (for mean-IC metric) the resampled statistic as a simple mean:

$$\hat{\theta}_h^{*(b)} = \mathrm{nanmean}(\{ x_{h, t_j} \}_{j=1}^{n}).$$

See `reality_check`.

### E.3 Romano–Wolf (implemented, opt-in)

When `CRYPTO_ANALYZER_ENABLE_ROMANOWOLF=1`, the repo runs the Romano–Wolf maxT stepdown on the same joint null matrix used for RC. Adjusted p-values are monotone non-decreasing in stepdown order; see `_romano_wolf_stepdown` in `reality_check`. **Output contract:** `rw_adjusted_p_values` is absent when RW is disabled; when enabled and the full null matrix is available (not loaded from cache without it), it is a Series/dict hypothesis_id → adjusted p-value. When cache is used and the full matrix is not stored, `rw_adjusted_p_values` may be empty. `stats_overview.json` includes `rw_enabled` (bool).

---

## F. Effective trials (Neff) and DSR default

When reportv2 is run with `--n-trials auto`, the repo builds the strategy return matrix $R$ (T×J) from `portfolio_pnls`, computes the correlation matrix, and uses `effective_trials_eigen` (eigenvalue participation ratio) as $N_{\mathrm{eff}}$; see `multiple_testing`. That value is passed into DSR as the trial count. Strategies with insufficient valid data are dropped before computing Neff; the number of columns used is recorded.

**Artifact keys:** `n_trials_user` (null if auto), `n_trials_eff_eigen` (null if user-specified), `n_trials_used`, `n_trials_eff_inputs_total`, `n_trials_eff_inputs_used`.

---

## G. HAC mean inference (Newey–West)

The repo implements `hac_mean_inference(x, L, min_obs=30)` in `crypto_analyzer/statistics.py`: Newey–West long-run variance with Bartlett weights, then $t = \bar{x}\sqrt{n}/\sqrt{\Omega}$, $p = 2(1 - \Phi(|t|))$. When `L` is None, $L = \lfloor 4(n/100)^{2/9} \rfloor$ capped by $n/3$. When $n < 30$, the function returns null t/p and `hac_skipped_reason: "n < 30"`. Non-finite HAC variance also sets a skip reason. The function returns `t_hac`, `p_hac`; reportv2 maps these to `t_hac_mean_return`, `p_hac_mean_return` in stats_overview. This is inference on the **mean** (e.g. mean return or mean IC), not full finite-sample Sharpe.

**Artifact keys:** `hac_lags_used`, `t_hac_mean_return`, `p_hac_mean_return`, `hac_skipped_reason`.

---

## H. CSCV PBO (canonical)

The repo implements `pbo_cscv(R, S, seed, max_splits, metric)` in `crypto_analyzer/multiple_testing.py`. Data (matrix $R$ T×J) is split into $S$ equal blocks; $S$ must be even. **Split construction:** The code uses $n_{\mathrm{splits}} = \min(\binom{S}{S/2}, \mathrm{max\_splits})$ iterations; each iteration draws a random permutation of block indices (train = first $S/2$, test = second $S/2$). Splits are thus always random partitions, not full enumeration of $\binom{S}{S/2}$ (deterministic for fixed seed). When $\binom{S}{S/2} > \mathrm{max\_splits}$, only $\mathrm{max\_splits}$ such random splits are used. For each split: rank strategies by in-sample metric, take the winner’s OOS rank, $\lambda = \mathrm{logit}(\mathrm{rank}/J)$; PBO = fraction of splits with $\lambda < 0$. Midrank used for ties. **Skip:** When $T < S \times 4$, or $J < 2$, or $S$ odd, the function returns a dict with `pbo_cscv_skipped_reason` and no `pbo_cscv` value.

**Artifact keys:** `pbo_cscv`, `pbo_cscv_blocks` (n_blocks), `pbo_cscv_total_splits`, `pbo_cscv_splits_used` (n_splits), `pbo_metric`; when skipped: `pbo_cscv_skipped_reason`. Known deviation: see [alignment audit](../audit/methods_implementation_alignment.md#known-deviations--todo-for-future).

---

## I. Structural break diagnostics

The repo implements CUSUM mean-shift (HAC-calibrated) and sup-Chow single-break scan in `crypto_analyzer/structural_breaks.py`. **CUSUM:** `calibration_method`: "HAC"; min obs 20 (`CUSUM_MIN_OBS`). **Sup-Chow:** `calibration_method`: "asymptotic"; min obs 100 (`SCAN_MIN_OBS`). Each test returns `test_name`, `stat`, `p_value`, `break_suspected`, `estimated_break_index`, `estimated_break_date` (index converted to date via series index, UTC→naive, format `%Y-%m-%dT%H:%M:%S`). When skipped (e.g. n too small, non-finite variance): `skipped_reason` set, `break_suspected` false, stat/p/date null. `run_break_diagnostics(series_dict)` returns `{"series": { series_name: [cusum_entry, scan_entry], ... }, "hac_lags": ...}`; each entry includes `series_name`. `stats_overview`: `break_diagnostics_written`, `break_diagnostics_skipped_reason`.

---

## J. Capacity curve (participation-based impact)

The repo implements `capacity_curve()` in `execution_cost`. **Impact:** When `use_participation_impact=True`, participation proxy = $\min(\mathrm{max\_pct},\; m \cdot \overline{\mathrm{turnover}} \times 100)$; impact_bps = linear in participation (via `impact_bps_from_participation`), capped. When False, impact_bps = $\mathrm{impact\_k} \cdot m^{\mathrm{impact\_alpha}}$. Net returns = gross − (fee + slippage + spread + impact) applied to turnover; then Sharpe and optional columns per multiplier. **CSV contract:** First two columns `notional_multiplier`, `sharpe_annual` (required, order fixed); extra columns additive only (`mean_ret_annual`, `vol_annual`, `avg_turnover`, `est_cost_bps`, `impact_bps`, `spread_bps`). Non-monotone behavior is not forced: `capacity_curve_is_non_monotone()` detects strict increase in `sharpe_annual` on consecutive rows; reportv2 sets `non_monotone_capacity_curve_observed` in stats_overview. `execution_evidence.json` cost_config must match the model used (participation params when participation-based).

**Artifact keys:** `capacity_curve_written`, `non_monotone_capacity_curve_observed`; capacity curve CSV; execution_evidence JSON with `cost_config`, `capacity_curve_path`.

---

## K. "Methods & Limits" summary (what to claim safely)

- **DSR** here is a screening statistic using an i.i.d.-style Sharpe variance approximation with skew/excess kurtosis and a leading-order extreme-value correction $\sqrt{2 \ln N}$ (see `multiple_testing`). When `--n-trials auto`, $N$ is set from effective trials (eigenvalue ratio). It is not a full, formally calibrated multiple-testing p-value.
- **BH/BY** are standard FDR adjustments; BY's harmonic inflation $c_m$ makes it valid under arbitrary dependence and asymptotically costs a $\ln m$ factor (see `multiple_testing_adjuster`).
- **PBO proxy** is a heuristic "median underperformance rate" across walk-forward splits (see `multiple_testing`). **CSCV PBO** is implemented separately: P($\lambda < 0$) with random-permutation splits (see §H and [alignment audit](../audit/methods_implementation_alignment.md)); skipped when T &lt; S×4 or J &lt; 2 with reason in artifacts.
- **Bootstrap** uses fixed or stationary blocks; stationary bootstrap uses geometric block lengths with mean $\ell$ and wrap-around (see `statistics`).
- **Reality Check** is implemented as a max-statistic bootstrap test with dependence preserved by sharing resampling indices across hypotheses, and p-value $(1 + \bigl\lvert \lbrace T^* \geq T \rbrace \bigr\rvert) / (B + 1)$; see `reality_check`. **Romano–Wolf** stepdown is implemented (opt-in env flag); outputs `rw_adjusted_p_values` when enabled.
- **HAC mean inference** is Newey–West LRV for the mean; skipped when n &lt; 30 with `hac_skipped_reason`; see `crypto_analyzer/statistics.py`.
- **Break diagnostics:** CUSUM (HAC) and sup-Chow (asymptotic) in `crypto_analyzer/structural_breaks.py`; skip reasons and `estimated_break_date` in `break_diagnostics.json`.
- **Capacity curve:** Participation-based impact (or power-law fallback); required CSV columns; `non_monotone_capacity_curve_observed` flag; execution_evidence cost_config must match.
