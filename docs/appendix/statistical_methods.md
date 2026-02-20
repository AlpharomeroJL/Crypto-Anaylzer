# Appendix A — Statistical Methods, Formal Definitions, and Assumptions

This appendix provides formal definitions of the statistical procedures used in Crypto-Analyzer's research validation framework. The objective is to rigorously control selection bias, overfitting, and false discoveries in systematic signal research under temporal and cross-sectional dependence.

## A.1 Notation and Setup

Let:

- $r_t$ denote portfolio returns at time $t$, $t = 1, \ldots, T$.
- $\hat{\mu} = \frac{1}{T} \sum_{t=1}^{T} r_t$ denote the sample mean.
- $\hat{\sigma}^2 = \frac{1}{T-1} \sum_{t=1}^{T} (r_t - \hat{\mu})^2$ denote the sample variance.
- $SR = \frac{\hat{\mu}}{\hat{\sigma}}$ denote the sample Sharpe ratio (assuming zero risk-free rate).
- $m$ denote the number of tested signals.
- $p_i$ denote the p-value of signal $i$.

Unless otherwise stated, all performance statistics are computed strictly out-of-sample under walk-forward validation.

## A.2 Walk-Forward Evaluation

### A.2.1 Procedure

Let the full sample be partitioned into $K$ sequential folds:

$$\{1, \ldots, T\} = \bigcup_{k=1}^{K} F_k$$

For each fold $k$:

- **Training set:** $\mathcal{T}_k$
- **Test set:** $\mathcal{V}_k$
- With $\max(\mathcal{T}_k) < \min(\mathcal{V}_k)$.

Model parameters $\theta_k$ are estimated only on $\mathcal{T}_k$:

$$\theta_k = \arg\max_{\theta} \, L(\theta; r_t, \, t \in \mathcal{T}_k)$$

Performance is evaluated exclusively on $\mathcal{V}_k$. Final out-of-sample performance is aggregated across all $\mathcal{V}_k$.

### A.2.2 Assumptions

- No leakage between training and validation.
- Feature engineering is strictly backward-looking.
- Approximate stationarity within each fold.

### A.2.3 Limitations

- Does not control multiple testing bias.
- Does not protect against regime breaks.
- Parameter instability may remain undetected.

## A.3 Deflated Sharpe Ratio (DSR)

### A.3.1 Motivation

When selecting the best strategy among many candidates, the observed Sharpe ratio is upward biased. Bailey & López de Prado (2014) formalize a correction accounting for:

- Non-normal returns (skewness $\gamma_3$, kurtosis $\gamma_4$)
- Multiple testing
- Finite sample effects

### A.3.2 Sharpe Distribution Approximation

Under IID assumptions:

$$\sqrt{T} \cdot SR \sim N\left(\frac{\mu}{\sigma}, 1\right)$$

However, under non-normality, variance of the Sharpe estimator becomes:

$$\text{Var}(SR) \approx \frac{1}{T} \left( 1 + \frac{1}{2} SR^2 - \gamma_3 SR + \frac{\gamma_4 - 3}{4} SR^2 \right)$$

### A.3.3 Expected Maximum Sharpe Under Multiple Trials

Let $N$ denote the number of independent trials. The expected maximum Sharpe under noise is approximated as:

$$E[SR_{\max}] \approx \mu_{SR} + \sigma_{SR} \cdot z_{1 - 1/N}$$

where $z_{1 - 1/N}$ is the standard normal quantile, and $\mu_{SR}$, $\sigma_{SR}$ are the Sharpe estimator mean and variance under the null.

### A.3.4 Deflated Sharpe Ratio

The Deflated Sharpe Ratio is:

$$DSR = \frac{SR - E[SR_{\max}]}{\sqrt{\text{Var}(SR)}}$$

The associated p-value is:

$$p = 1 - \Phi(DSR)$$

where $\Phi$ is the standard normal CDF.

### A.3.5 Assumptions

- Approximate IID or weak dependence.
- Accurate estimate of effective $N$.
- Finite fourth moment.

### A.3.6 Limitations

- $N$ is rarely known precisely.
- Cross-correlated signals violate independence.
- Approximation quality deteriorates under strong serial dependence.

## A.4 Probability of Backtest Overfitting (PBO)

### A.4.1 Setup

Divide sample into $S$ equal blocks:

$$\{1, \ldots, T\} = \bigcup_{s=1}^{S} B_s$$

For each combination of $S/2$ blocks:

- **Training blocks:** $B_{\mathrm{train}}$
- **Testing blocks:** $B_{\mathrm{test}}$

For each candidate strategy $j$: $SR_j^{\mathrm{train}}$, $SR_j^{\mathrm{test}}$.

### A.4.2 Ranking Procedure

Let:

$$j^* = \arg\max_{j} \, SR_j^{\mathrm{train}}$$

Compute its percentile rank in test performance:

$$\lambda = \frac{\text{rank}(SR_{j^*}^{\mathrm{test}})}{m}$$

Define:

$$\omega = \log\left( \frac{\lambda}{1 - \lambda} \right)$$

### A.4.3 PBO Definition

$$PBO = P(\omega < 0)$$

i.e., probability that the selected strategy performs below the median out-of-sample.

### A.4.4 Assumptions

- Block stationarity.
- Sufficient block count.
- Stable ranking metric.

### A.4.5 Limitations

- Computationally intensive (combinatorial growth).
- Sensitive to block construction.
- Does not control FDR across signals.

## A.5 False Discovery Rate (FDR) Control

### A.5.1 Benjamini–Hochberg (BH)

Given ordered p-values:

$$p_{(1)} \leq p_{(2)} \leq \cdots \leq p_{(m)}$$

Define:

$$k = \max\left\{ i : p_{(i)} \leq \frac{i}{m} \alpha \right\}$$

Reject all $p_{(i)} \leq p_{(k)}$. Controls:

$$FDR = E\left[ \frac{V}{R} \right] \leq \alpha$$

where $V$ = false positives, $R$ = total rejections.

### A.5.2 Benjamini–Yekutieli (BY)

Under arbitrary dependence:

$$p_{(i)} \leq \frac{i}{m} \cdot \frac{\alpha}{c(m)}$$

where:

$$c(m) = \sum_{j=1}^{m} \frac{1}{j}$$

BY is strictly more conservative.

### A.5.3 Assumptions

- **BH:** independence or positive dependence.
- **BY:** arbitrary dependence.

### A.5.4 Limitations

- Reduced power when $m$ is large.
- Controls expected FDR, not probability of any false discovery.

## A.6 Stationary Bootstrap

### A.6.1 Motivation

Returns exhibit serial dependence and volatility clustering. IID bootstrap is invalid.

### A.6.2 Procedure (Politis & Romano, 1994)

Let block length $L$ follow a geometric distribution:

$$P(L = k) = p(1 - p)^{k - 1}$$

Expected block length:

$$E[L] = \frac{1}{p}$$

Resample blocks with replacement to generate bootstrap series.

### A.6.3 Bootstrap Confidence Interval

For statistic $\theta$: $\{\theta^{*(b)}\}_{b=1}^{B}$. CI at level $1 - \alpha$:

$$\left[ \theta^{*(\alpha/2)}, \, \theta^{*(1 - \alpha/2)} \right]$$

### A.6.4 Assumptions

- Weak stationarity.
- Mixing conditions.
- Finite variance.

### A.6.5 Limitations

- Block parameter choice impacts bias/variance tradeoff.
- Regime shifts violate stationarity.
- Heavy tails may distort CI coverage.

## A.7 Effective Number of Independent Trials

Given correlation matrix $\Sigma$ of signal returns with eigenvalues $\lambda_1, \ldots, \lambda_m$, effective number of trials is approximated via:

$$N_{\mathrm{eff}} = \frac{\left( \sum_{i=1}^{m} \lambda_i \right)^2}{\sum_{i=1}^{m} \lambda_i^2}$$

This reduces inflation when signals are correlated.

## A.8 Null Suite (Placebo Testing)

Define synthetic signals: random permutations, lag shifts, sign inversions. If placebo signals survive validation gates, thresholds are tightened. This acts as an empirical analogue to White's Reality Check (2000).

## A.9 Method Interaction Hierarchy

A signal is promoted only if:

1. Positive out-of-sample Sharpe.
2. $DSR > z_{1-\alpha}$.
3. Survives BH or BY correction.
4. Acceptable PBO.
5. Bootstrap CI excludes zero.
6. Fails null suite equivalence.

All conditions are required.

## A.10 Global Limitations

This framework does not guarantee:

- Economic viability after impact and slippage.
- Stability under structural breaks.
- Absence of model misspecification.
- Future profitability.

It provides probabilistic control of: selection bias, false discovery rate, and backtest overfitting visibility.

## References

- Bailey, D., & López de Prado, M. (2014). The Deflated Sharpe Ratio.
- Bailey, D., Borwein, J., López de Prado, M., & Zhu, Q. (2014). The Probability of Backtest Overfitting.
- Benjamini, Y., & Hochberg, Y. (1995). Controlling the False Discovery Rate.
- Benjamini, Y., & Yekutieli, D. (2001). The Control of the False Discovery Rate Under Dependency.
- Politis, D., & Romano, J. (1994). The Stationary Bootstrap.
- White, H. (2000). A Reality Check for Data Snooping.

---

# Appendix B — Derivations and Asymptotic Results (Proof Sketches)

This appendix expands key derivations and asymptotic arguments underpinning the procedures in Appendix A. Full proofs appear in the cited primary sources; we provide derivation steps and proof skeletons sufficient for audit and implementation review.

## B.1 Asymptotics for Sample Mean and Variance (Weak Dependence)

Let $\{r_t\}_{t \in \mathbb{Z}}$ be strictly stationary with $E[r_t] = \mu$, $\text{Var}(r_t) = \sigma^2$, and satisfying a mixing condition (e.g., strong mixing with summable mixing coefficients) plus $E|r_t|^{2+\delta} < \infty$ for some $\delta > 0$.

Define:

$$\hat{\mu} = \frac{1}{T} \sum_{t=1}^{T} r_t, \qquad \hat{\sigma}^2 = \frac{1}{T} \sum_{t=1}^{T} (r_t - \hat{\mu})^2 \quad \text{(population-style; } T^{-1} \text{ differences are } o(1)\text{)}.$$

**Proposition B.1 (CLT for $\hat{\mu}$).** Under the conditions above:

$$\sqrt{T} \, (\hat{\mu} - \mu) \xrightarrow{d} N(0, \Omega),$$

where the long-run variance is

$$\Omega = \gamma(0) + 2 \sum_{k=1}^{\infty} \gamma(k), \qquad \gamma(k) = \text{Cov}(r_t, r_{t-k}).$$

*Proof sketch.* Apply a central limit theorem for stationary mixing sequences (e.g., Ibragimov–Linnik type results). The variance of the partial sums includes all autocovariances; scaling by $T^{-1}$ yields $\Omega$. □

*Implementation note.* If you treat returns as IID, $\Omega = \sigma^2$. Under dependence, replace IID standard errors with HAC-type estimates when computing p-values from mean returns.

## B.2 Delta-Method Derivation for Sharpe Ratio Asymptotics

Define the (zero risk-free) Sharpe statistic:

$$SR = \frac{\hat{\mu}}{\hat{\sigma}}.$$

Let $\theta = (\mu, \sigma)$ and $\hat{\theta} = (\hat{\mu}, \hat{\sigma})$. Define $g(\mu, \sigma) = \mu/\sigma$. Then $SR = g(\hat{\theta})$. Assume IID for the cleanest derivation; weak dependence extensions replace the covariance matrix with its long-run analogue.

### B.2.1 Joint asymptotics of $(\hat{\mu}, \hat{\sigma})$

Under IID with finite fourth moment:

$$\sqrt{T} \begin{pmatrix} \hat{\mu} - \mu \\ \hat{\sigma} - \sigma \end{pmatrix} \xrightarrow{d} N\left( \begin{pmatrix} 0 \\ 0 \end{pmatrix}, \Sigma_{\mu,\sigma} \right).$$

A convenient route is to use $(\hat{\mu}, \widehat{m_2})$ where $\widehat{m_2} = \frac{1}{T} \sum (r_t - \mu)^2$, then map to $\hat{\sigma} = \sqrt{ \widehat{m_2} - (\hat{\mu} - \mu)^2 }$. To first order, $\hat{\sigma} \approx \sqrt{\widehat{m_2}}$.

For IID:

- $\text{Var}(\hat{\mu}) = \sigma^2 / T$
- $\text{Var}(\widehat{m_2}) = (\mu_4 - \sigma^4) / T$, where $\mu_4 = E[(r - \mu)^4]$
- $\text{Cov}(\hat{\mu}, \widehat{m_2}) = \mu_3 / T$, where $\mu_3 = E[(r - \mu)^3]$

### B.2.2 Apply the Delta Method

Gradient:

$$\nabla g(\mu, \sigma) = \left( \frac{\partial}{\partial\mu} \frac{\mu}{\sigma}, \; \frac{\partial}{\partial\sigma} \frac{\mu}{\sigma} \right) = \left( \frac{1}{\sigma}, \; -\frac{\mu}{\sigma^2} \right).$$

Thus:

$$\sqrt{T} \, (SR - \mu/\sigma) \xrightarrow{d} N\left( 0, \; \nabla g^\top \Sigma_{\mu,\sigma} \nabla g \right).$$

Carrying out the multiplication (and expressing moments via standardized skewness and kurtosis) yields the widely used approximation (as in Bailey & López de Prado's development of Sharpe uncertainty corrections; see Deep Research Review of Alpharo…):

Let $\gamma_3 = \mu_3 / \sigma^3$, $\gamma_4 = \mu_4 / \sigma^4$. Then an approximate large-$T$ variance for the sample Sharpe is:

$$\text{Var}(SR) \approx \frac{1}{T} \left( 1 - \gamma_3 SR + \frac{\gamma_4 - 1}{4} SR^2 \right).$$

Many texts present close variants depending on (i) population vs sample variance, (ii) whether you keep $O(T^{-1})$ terms from $(\hat{\mu} - \mu)^2$, and (iii) whether kurtosis is excess kurtosis $\kappa = \gamma_4 - 3$. The key point: nonzero skewness and excess kurtosis increase Sharpe estimator variance, which feeds DSR-style corrections. □

*Practical guidance.* In code, compute $\gamma_3, \gamma_4$ on OOS returns. Under serial dependence, treat this as optimistic unless you use block/bootstrap/HAC adjustments.

## B.3 Expected Maximum of $N$ “Sharpe-like” Trials (Extreme Value Approximation)

DSR uses an estimate of the expected maximum performance among $N$ trials under a null model.

Let $Z_1, \ldots, Z_N$ be IID standard normal and $M_N = \max_i Z_i$. Then:

$$E[M_N] \approx b_N + \gamma \, a_N,$$

where $\gamma \approx 0.57721$ is the Euler–Mascheroni constant and

$$b_N = \sqrt{2 \ln N} - \frac{\ln\ln N + \ln(4\pi)}{2\sqrt{2\ln N}}, \qquad a_N = \frac{1}{\sqrt{2\ln N}}.$$

*Derivation sketch.* Use the normal tail approximation $1 - \Phi(x) \sim \phi(x)/x$. Solve $P(M_N \leq x) = \Phi(x)^N \approx \exp(-N(1 - \Phi(x)))$. Choose $x = b_N + y/a_N$ to normalize $M_N$ so that $P((M_N - b_N) a_N \leq y) \to \exp(-e^{-y})$ (Gumbel). Take expectations of the limiting Gumbel distribution: $E[Y] = \gamma$. □

*Mapping to Sharpe.* If under the null the Sharpe estimator is approximately normal, $SR \approx N(\mu_{SR}, \sigma_{SR}^2)$, then:

$$E[\max SR] \approx \mu_{SR} + \sigma_{SR} \, E[M_N].$$

This is the “expected best luck” term subtracted inside DSR-style deflation (see the DSR reference context in Deep Research Review of Alpharo…).

## B.4 DSR: Expanded Construction and Asymptotic Interpretation

Define: observed out-of-sample Sharpe $SR_{\mathrm{obs}}$; null Sharpe mean $\mu_{SR}$ (often 0); null Sharpe sd $\sigma_{SR} \approx \sqrt{\text{Var}(SR)}$; trial count $N$ (or $N_{\mathrm{eff}}$).

Then:

$$SR^* = E[\max SR_{\mathrm{null}}] \approx \mu_{SR} + \sigma_{SR} \, E[M_N]$$

and the deflated z-score:

$$DSR = \frac{SR_{\mathrm{obs}} - SR^*}{\sigma_{SR}}.$$

**Proposition B.2 (Asymptotic meaning).** Under the null and the approximations above, $DSR$ is asymptotically standard normal, so $p \approx 1 - \Phi(DSR)$.

*Proof sketch.* Under the null, $SR_{\mathrm{obs}}$ is asymptotically normal via B.2. $SR^*$ is a deterministic function of $T$ and $N$ (plug-in estimate). Standardize by $\sigma_{SR}$ to obtain an approximately normal statistic. □

*Caveat.* Correlated trials violate IID assumptions behind $E[M_N]$. Using $N_{\mathrm{eff}}$ (Appendix A) is an attempt to restore a valid extreme-value scale, but it remains an approximation.

## B.5 BH FDR Control: Proof Skeleton (Independent Case)

Let $H_1, \ldots, H_m$ be hypotheses with p-values $p_1, \ldots, p_m$. Let $m_0$ be the number of true nulls. BH at level $\alpha$ rejects all $p_{(i)} \leq \frac{i}{m} \alpha$.

Define: $V$ = number of false rejections; $R$ = total rejections; $FDR = E[V / \max(R, 1)]$.

**Theorem B.3 (BH under independence).** If null p-values are IID $\mathrm{Uniform}(0,1)$ and independent of non-null p-values, then:

$$FDR \leq \frac{m_0}{m} \alpha \leq \alpha.$$

*Proof outline (standard).* Condition on the non-null p-values and on the set of null indices. Use the self-consistency property of BH: if a null p-value is rejected, it must be $\leq \alpha R/m$. Show:

$$E\left[ \frac{V}{\max(R,1)} \right] = \sum_{i \in H_0} E\left[ \frac{\mathbf{1}\{p_i \leq \alpha R/m\}}{\max(R,1)} \right].$$

Under independence and uniformity, for each null $i$: $E\bigl[ \mathbf{1}\{p_i \leq \alpha R/m\} / \max(R,1) \bigr] \leq \alpha/m$. Summing over $m_0$ nulls yields $(m_0/m)\alpha$. □

*Relevance.* This is why BH is attractive when p-values are “close enough” to independent or PRDS (positive regression dependency).

## B.6 BY Under Arbitrary Dependence: Where the Harmonic Term Comes From

BY modifies the BH threshold by dividing $\alpha$ by $c(m) = \sum_{j=1}^{m} \frac{1}{j}$.

**Theorem B.4 (BY).** Under arbitrary dependence among p-values, BY controls FDR at level $\alpha$.

*Proof outline (standard).* Use a union-bound style argument over possible rejection set sizes. Replace the sharp independence-based expectation step in BH with a bound that holds for any dependence. The bound introduces a factor $\sum_{k=1}^{m} 1/k$ from summing over possible numbers of rejections $R = k$. Tighten to yield the BY threshold. □

*Interpretation.* The harmonic factor is the “price of dependence-robustness,” making BY conservative when tests are strongly correlated.

## B.7 Stationary Bootstrap Consistency (Why It Works)

The stationary bootstrap (Politis & Romano) samples blocks of random length $L \sim \mathrm{Geom}(p)$, concatenated to length $T$.

**Proposition B.5 (Consistency for smooth functionals; sketch).** For weakly dependent, strictly stationary $\{r_t\}$ satisfying mixing and moment conditions, with block length $E[L] = 1/p \to \infty$ while $E[L]/T \to 0$, the stationary bootstrap distribution of many statistics (sample mean, autocovariances, smooth functionals) converges to the correct asymptotic distribution.

*Proof sketch.* Random blocks preserve local dependence structure up to typical block length. As $E[L] \to \infty$, within-block dependence increasingly matches the true process. As $E[L]/T \to 0$, enough blocks are sampled to average out block boundary effects. Use coupling + mixing to show the bootstrap partial sum process approximates the original in distribution. □

*Practical parameter rule.* Choose $E[L]$ large enough to capture dependence (e.g., volatility clustering horizon), but small enough to include many blocks.

## B.8 PBO / CSCV: Why the Logit Transform Appears

In CSCV, for each split $s$, compute the OOS percentile rank $\lambda_s \in (0,1)$ of the strategy selected by IS optimization. Define:

$$\omega_s = \log\left( \frac{\lambda_s}{1 - \lambda_s} \right).$$

**Proposition B.6 (Median criterion equivalence).** $\omega_s < 0 \;\Longleftrightarrow\; \lambda_s < 1/2$. Thus:

$$PBO = P(\omega < 0) = P(\lambda < 1/2).$$

*Reason for logit.* $\lambda$ is bounded on $(0,1)$; the logit maps it to $\mathbb{R}$, improving symmetry and enabling diagnostic plots and averaging on an unbounded scale.

*Asymptotic note.* If the IS-selected strategy has no genuine edge, then $\lambda$ tends to behave like a uniform random rank, making $P(\lambda < 1/2) \approx 1/2$. Observed PBO substantially above $1/2$ indicates systematic OOS rank deterioration (overfitting).

## B.9 Effective Trials: Eigenvalue Derivation for $N_{\mathrm{eff}}$

Given a correlation (or covariance) matrix $\Sigma$ for signal returns with eigenvalues $\lambda_1, \ldots, \lambda_m$:

$$N_{\mathrm{eff}} = \frac{\left( \sum_{i=1}^{m} \lambda_i \right)^2}{\sum_{i=1}^{m} \lambda_i^2}.$$

*Derivation intuition.* If signals are independent with equal variance, $\Sigma$ is identity, $\lambda_i = 1$, so $N_{\mathrm{eff}} = m^2/m = m$. If signals are perfectly collinear, one eigenvalue $\lambda_1 = m$, rest 0, so $N_{\mathrm{eff}} = m^2/m^2 = 1$. Thus $N_{\mathrm{eff}}$ interpolates between 1 and $m$, acting as a trial-count shrinkage under correlation.

## B.10 What to Claim (Strict Wording)

To keep the README and docs academically honest:

- Say **“DSR-style correction using extreme-value approximation for the expected max under $N_{\mathrm{eff}}$ trials,”** unless you exactly match every modeling assumption in the original derivation.
- Say **“PBO-style estimate via block cross-validation,”** unless you implement full CSCV enumeration.
- Say **“BH/BY control FDR under (independence / arbitrary dependence) given valid p-values,”** and note p-values under dependence require HAC/bootstrap/randomization for strict validity.

## References (Proof Sources)

These proof skeletons correspond to the canonical references already listed in your review and Methods docs (Deep Research Review of Alpharo…): DSR, PBO, BH/BY, stationary bootstrap, Reality Check.
