# Page 1 — Executive-Level Signal Framing

Generated: 2026-02-20 09:04 UTC
Freq: 1h  Signals: liquidity_shock_reversion  Portfolio: advanced  Case study: liqshock

## Executive Summary
- OOS Sharpe: N/A (insufficient data or unstable estimates).

## Research Design Overview
- Artifacts keyed by `run_id`; deterministic reruns supported via `CRYPTO_ANALYZER_DETERMINISTIC_TIME`.
- RC uses fixed seed (42) and caches null distributions keyed by family id.

**Assumptions**
- Execution assumed at t+1 bar (as-of lag 1 bar).
- No forward-looking liquidity measures used.

## Data & Universe
- Returns columns: 3; bars columns matched: 3 (100.0%).
- No forward-looking liquidity measures used.
- Results shown are computed over the full available evaluation window; walk-forward splitting is configured but not enabled in this run.

## Signal Construction
Liquidity shock reversion: `dlog(L)` over N bars, cross-sectional winsorize and z-score, then negate (buy after liquidity drops). Grid: N ∈ {6, 12, 24, 48}, winsor_p ∈ {0.01, 0.05}, clip ∈ {3, 5}. Headline horizon: 1 bar.

## Experimental Controls
- Orthogonalization skipped for liqshock-only run (case-study mode).
- **Factor disclosure:** Factor fitting is not restricted to train window per fold in this run.

## False Discoveries Rejected
*Sharpe computed from the advanced portfolio config (OOS), annualized per reportv2 conventions.*

*No raw p-values available for variants.*

Parameter grid tested: 16 variants. Survived correction: N/A.

RC family p-value: 0.0050 (single family-level number).

*Small sample size in this dataset may cause unstable estimates; results are illustrative.*

## Top 10 most valuable pairs
*Valuable = economically meaningful (stable liquidity, enough activity) + statistically informative (enough shock events, low missingness).*

| Pair | median_liquidity_usd | p10_liquidity_usd | missing_pct | event_rate | opportunity_score |
|------|---------------------|-------------------|-------------|------------|-------------------|
| solana:Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE | 25234794 | 24459182 | 0.0 | 0.0000 | 0 |

## Tradability / Capacity
Capacity curves (per variant):
- `reports\csv\capacity_curve_liqshock_N6_w0.01_clip3_dfec6ca73321085a.csv`
- `reports\csv\capacity_curve_liqshock_N6_w0.01_clip5_dfec6ca73321085a.csv`
- `reports\csv\capacity_curve_liqshock_N6_w0.05_clip3_dfec6ca73321085a.csv`
- `reports\csv\capacity_curve_liqshock_N6_w0.05_clip5_dfec6ca73321085a.csv`
- `reports\csv\capacity_curve_liqshock_N12_w0.01_clip3_dfec6ca73321085a.csv`
- `reports\csv\capacity_curve_liqshock_N12_w0.01_clip5_dfec6ca73321085a.csv`
- `reports\csv\capacity_curve_liqshock_N12_w0.05_clip3_dfec6ca73321085a.csv`
- `reports\csv\capacity_curve_liqshock_N12_w0.05_clip5_dfec6ca73321085a.csv`
- `reports\csv\capacity_curve_liqshock_N24_w0.01_clip3_dfec6ca73321085a.csv`
- `reports\csv\capacity_curve_liqshock_N24_w0.01_clip5_dfec6ca73321085a.csv`
- `reports\csv\capacity_curve_liqshock_N24_w0.05_clip3_dfec6ca73321085a.csv`
- `reports\csv\capacity_curve_liqshock_N24_w0.05_clip5_dfec6ca73321085a.csv`
- `reports\csv\capacity_curve_liqshock_N48_w0.01_clip3_dfec6ca73321085a.csv`
- `reports\csv\capacity_curve_liqshock_N48_w0.01_clip5_dfec6ca73321085a.csv`
- `reports\csv\capacity_curve_liqshock_N48_w0.05_clip3_dfec6ca73321085a.csv`
- `reports\csv\capacity_curve_liqshock_N48_w0.05_clip5_dfec6ca73321085a.csv`

## Risk / failure modes
- Liquidity panel limited to bars matched to returns; thin universe may reduce power.
- Single-horizon (1 bar) headline; multi-horizon results in appendix if produced.

## Sober conclusion
Results are conditional on the chosen grid and evaluation period. BH correction applied to the 16-variant liqshock grid only (case-study mode). Replication: use the same run_id and deterministic seed for RC.
