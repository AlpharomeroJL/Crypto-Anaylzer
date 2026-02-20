"""
Case-study memo renderer for liquidity-shock-reversion (16 variants).
Produces Page 1/2/3 memo with BH table, Top 10 pairs, and institutional boilerplate.
Used only when reportv2 is invoked with --case-study liqshock.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from crypto_analyzer.multiple_testing_adjuster import adjust as adjust_pvalues
from crypto_analyzer.signals_xs import winsorize_cross_section, zscore_cross_section

# Canonical event definition for Top 10 (same formula as signal, pre-negation z < -2)
_LIQSHOCK_TOP10_N = 6
_LIQSHOCK_TOP10_WINSOR = 0.05
_LIQSHOCK_TOP10_CLIP = 3.0
_P10_LIQUIDITY_FLOOR = 250_000  # USD
_MISSING_PCT_MAX = 10.0
_TOP_PCT_MEDIAN_DROP = 5.0  # drop top 5% by median liq


def _raw_z_pre_negation(
    liquidity_panel: pd.DataFrame,
    oos_index: pd.Index,
    columns: pd.Index,
    N: int = _LIQSHOCK_TOP10_N,
    winsor_p: float = _LIQSHOCK_TOP10_WINSOR,
    clip: float = _LIQSHOCK_TOP10_CLIP,
) -> pd.DataFrame:
    """Z-score of dlogL (before negation). Used for event-rate definition."""
    if liquidity_panel is None or liquidity_panel.empty:
        return pd.DataFrame(index=oos_index, columns=columns, dtype=float)
    common = liquidity_panel.columns.intersection(columns)
    if len(common) == 0:
        return pd.DataFrame(index=oos_index, columns=columns, dtype=float)
    liq = liquidity_panel.reindex(index=oos_index, columns=common).clip(lower=1.0)
    log_L = np.log(liq)
    dlogL = log_L.diff(N)
    dlogL = winsorize_cross_section(dlogL, p=winsor_p)
    z = zscore_cross_section(dlogL, clip=clip)
    return z.reindex(index=oos_index, columns=columns)


def _top10_valuable_pairs(
    returns_df: pd.DataFrame,
    liquidity_panel: pd.DataFrame | None,
    oos_index: pd.Index,
    p10_liq_floor: float = _P10_LIQUIDITY_FLOOR,
) -> list[dict[str, Any]]:
    """
    OOS-only: per-pair median liq, p10 liq, % missing, event_rate (z < -2 pre-negation).
    Eligibility: p10 >= p10_liq_floor (USD), missing% < 10%, drop top 5% by median liq.
    Score: event_rate * median_liq. Return top 10 (or fewer) rows.
    """
    if liquidity_panel is None or liquidity_panel.empty or returns_df.empty:
        return []
    cols = returns_df.columns
    liq = liquidity_panel.reindex(index=oos_index, columns=cols)
    raw_z = _raw_z_pre_negation(liquidity_panel, oos_index, cols)
    rows: list[dict[str, Any]] = []
    for c in cols:
        s = liq[c]
        median_liq = float(s.median())
        p10 = float(s.quantile(0.10)) if s.notna().any() else 0.0
        total = len(s)
        missing_or_zero_pct = 100.0 * ((~s.notna()) | (s <= 0)).sum() / total if total else 100.0
        zc = raw_z[c]
        extreme = (zc < -2).sum()
        event_rate = float(extreme / total) if total else 0.0
        rows.append(
            {
                "pair": str(c),
                "median_liquidity_usd": median_liq,
                "p10_liquidity_usd": p10,
                "missing_pct": missing_or_zero_pct,
                "event_rate": event_rate,
                "opportunity_score": event_rate * median_liq if np.isfinite(median_liq) else 0.0,
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return []
    # Eligibility
    df = df[df["p10_liquidity_usd"] >= p10_liq_floor]
    df = df[df["missing_pct"] < _MISSING_PCT_MAX]
    # Drop top 5% by median liq (no-op if few rows)
    if len(df) > 1:
        thresh = df["median_liquidity_usd"].quantile(1.0 - _TOP_PCT_MEDIAN_DROP / 100.0)
        df = df[df["median_liquidity_usd"] <= thresh]
    df = df.sort_values("opportunity_score", ascending=False).head(10)
    return df.to_dict("records")


def render_case_study_liqshock(
    *,
    args: Any,
    returns_df: pd.DataFrame,
    signals_dict: dict[str, pd.DataFrame],
    orth_dict: dict[str, pd.DataFrame],
    portfolio_pnls: dict[str, pd.Series],
    canonical_metrics: dict[str, Any],
    liquidity_panel: pd.DataFrame | None,
    roll_vol_panel: pd.DataFrame | None,
    bars_match_n_ret: int,
    bars_match_n_match: int,
    bars_match_pct: float,
    run_id: str,
    out_dir: Path,
    rc_result: dict | None = None,
    regime_run_id: str | None = None,
    regime_coverage_rel_path: str | None = None,
    top10_p10_liq_floor: int = 250000,
) -> str:
    """
    Build the full case-study memo markdown. Uses canonical_metrics for Sharpe and raw p;
    applies BH over liqshock variants only.
    """
    lines: list[str] = []
    freq = getattr(args, "freq", "1h")

    # ----- Page 1: Executive-Level Signal Framing -----
    lines.append("# Page 1 — Executive-Level Signal Framing\n")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"Freq: {freq}  Signals: {args.signals}  Portfolio: {args.portfolio}  Case study: liqshock")
    lines.append("")

    # Executive Summary (OOS-only headline numbers)
    lines.append("## Executive Summary")
    variants = [k for k in signals_dict if k.startswith("liqshock_")]
    has_finite_headline = False
    if variants and portfolio_pnls:
        sharpes = []
        for k in variants:
            sk = canonical_metrics.get(f"sharpe_{k}")
            if sk is not None and np.isfinite(sk):
                sharpes.append(float(sk))
        if sharpes:
            lines.append(f"- OOS Sharpe (1 bar, advanced portfolio): mean across variants = {np.mean(sharpes):.4f}")
            has_finite_headline = True
        if "sharpe" in canonical_metrics and np.isfinite(canonical_metrics.get("sharpe")):
            lines.append(f"- Aggregate portfolio Sharpe: {canonical_metrics['sharpe']:.4f}")
            has_finite_headline = True
    if not has_finite_headline and variants:
        lines.append(
            "- OOS Sharpe: N/A (insufficient data or unstable estimates; increase asset breadth/history for stable estimates)."
        )
    lines.append("")

    # Research Design Overview
    lines.append("## Research Design Overview")
    lines.append("- Artifacts are keyed by `run_id`; reruns can be pinned via `CRYPTO_ANALYZER_DETERMINISTIC_TIME`.")
    lines.append("- Reality Check uses fixed seed (42); null distributions are cached by family id.")
    lines.append("")
    lines.append("**Assumptions**")
    lines.append("- Execution assumed at t+1 bar (as-of lag 1 bar).")
    lines.append("- No forward-looking liquidity measures used.")
    lines.append("")

    # Data & Universe
    lines.append("## Data & Universe")
    lines.append(
        f"- Returns columns: {bars_match_n_ret}; bars columns matched: {bars_match_n_match} ({bars_match_pct:.1f}%)."
    )
    lines.append("- No forward-looking liquidity measures used.")
    lines.append("- Validation readiness depends on cross-sectional breadth and history length.")
    lines.append(
        "- **Recommended validation scale:** ≥25 assets and ≥1000 1h bars per asset for stable IC estimation."
    )
    lines.append(
        "- Walk-forward splitting is supported; this run uses the full evaluation window (walk-forward mode not enabled)."
    )
    lines.append("")

    # Signal Construction
    lines.append("## Signal Construction")
    lines.append(
        "Liquidity shock reversion: `dlog(L)` over N bars, cross-sectional winsorize and z-score, then negate (buy after liquidity drops). "
        "Grid: N ∈ {6, 12, 24, 48}, winsor_p ∈ {0.01, 0.05}, clip ∈ {3, 5}. Headline horizon: 1 bar."
    )
    lines.append("")

    # Experimental Controls
    lines.append("## Experimental Controls")
    lines.append("- Orthogonalization skipped for liqshock-only run (case-study mode).")
    lines.append(
        "- **Factor disclosure:** Factor fitting is not restricted to train window per fold in this run (unless strict-fold-factors is enabled)."
    )
    lines.append("")

    # ----- False Discoveries Rejected (variant-only BH) -----
    lines.append("## False Discoveries Rejected")
    lines.append("*Sharpe computed from the advanced portfolio config (OOS), annualized per reportv2 conventions.*")
    lines.append("")
    if not variants:
        lines.append("*No liqshock variants in this run.*")
    else:
        raw_p = {}
        for k in variants:
            pk = canonical_metrics.get(f"p_value_raw_{k}")
            if pk is not None and np.isfinite(pk):
                raw_p[k] = float(pk)
        if raw_p:
            p_series = pd.Series(raw_p)
            adj, _ = adjust_pvalues(p_series, method="bh", q=0.05)
            survived = (adj <= 0.05).sum()
            table_rows = ["| Variant | OOS Sharpe | BH-adjusted p | Status |"]
            table_rows.append("|---------|------------|---------------|--------|")
            for k in variants:
                sharpe = canonical_metrics.get(f"sharpe_{k}")
                sharpe_str = f"{sharpe:.4f}" if sharpe is not None and np.isfinite(sharpe) else "—"
                adj_p = adj.get(k)
                adj_p_str = f"{adj_p:.4f}" if adj_p is not None and np.isfinite(adj_p) else "—"
                status = "Survived" if (adj_p is not None and adj_p <= 0.05) else "Rejected"
                table_rows.append(f"| {k} | {sharpe_str} | {adj_p_str} | {status} |")
            for row in table_rows:
                lines.append(row)
            lines.append("")
            lines.append(f"Parameter grid tested: {len(variants)} variants. Survived correction: {int(survived)}.")
        else:
            lines.append("*No raw p-values available for variants.*")
            lines.append("")
            lines.append(f"Parameter grid tested: {len(variants)} variants. Survived correction: N/A.")
        # RC family p-value (always when we have variants, so memo is complete)
        if rc_result is not None and "rc_p_value" in rc_result:
            rcp = rc_result["rc_p_value"]
            if np.isfinite(rcp):
                lines.append("")
                lines.append(f"RC family p-value: {rcp:.4f} (single family-level number).")
            else:
                lines.append("")
                lines.append("RC family p-value: N/A (unstable or not computed).")
        else:
            lines.append("")
            lines.append("RC family p-value: N/A (RC not run in this configuration).")
        if not has_finite_headline or not raw_p:
            lines.append("")
            lines.append(
                "*Validation scale is currently below recommended thresholds; estimates may be unstable. "
                "Increase cross-sectional breadth and/or history for full-scale validation.*"
            )
    lines.append("")

    # ----- Top 10 most valuable pairs (OOS-only) -----
    lines.append("## Top 10 most valuable pairs")
    oos_index = returns_df.index
    top10 = _top10_valuable_pairs(returns_df, liquidity_panel, oos_index, p10_liq_floor=float(top10_p10_liq_floor))
    lines.append(
        "*Valuable = economically meaningful (stable liquidity/activity) + statistically informative (enough shock events, low missingness).*"
    )
    lines.append("")
    if not top10:
        lines.append(f"*No eligible pairs (p10 ≥ {top10_p10_liq_floor:,} USD, missing% < 10%, or insufficient data).*")
    else:
        if len(top10) < 5 and top10_p10_liq_floor >= 250000:
            lines.append("*Eligible pairs < 5; consider --top10-p10-liq-floor 100000 for broader coverage.*")
            lines.append("")
        table_rows = [
            "| Pair | median_liquidity_usd | p10_liquidity_usd | missing_pct | event_rate | opportunity_score |"
        ]
        table_rows.append(
            "|------|---------------------|-------------------|-------------|------------|-------------------|"
        )
        for r in top10:
            table_rows.append(
                f"| {r['pair']} | {r['median_liquidity_usd']:.0f} | {r['p10_liquidity_usd']:.0f} | "
                f"{r['missing_pct']:.1f} | {r['event_rate']:.4f} | {r['opportunity_score']:.0f} |"
            )
        for row in table_rows:
            lines.append(row)
    lines.append("")

    # Tradability / Capacity
    lines.append("## Tradability / Capacity")
    csv_dir = out_dir / "csv"
    capacity_paths = [str(csv_dir / f"capacity_curve_{name}_{run_id}.csv") for name in variants]
    if capacity_paths:
        lines.append("Capacity curves (per variant):")
        for p in capacity_paths[:20]:  # cap at 20 to avoid huge list
            lines.append(f"- `{p}`")
    else:
        lines.append("*No capacity curve paths (run with --execution-evidence).*")
    lines.append("")

    # Regime breakdown
    if regime_run_id and regime_coverage_rel_path:
        lines.append("## Regime breakdown")
        lines.append(f"Regime run: `{regime_run_id}`. Coverage: `{regime_coverage_rel_path}`.")
        lines.append("")

    # Risk / failure modes
    lines.append("## Risk / failure modes")
    lines.append("- Liquidity panel limited to bars matched to returns; thin universe may reduce power.")
    lines.append("- Single-horizon (1 bar) headline; multi-horizon results in appendix if produced.")
    lines.append("")

    # Sober conclusion
    lines.append("## Sober conclusion")
    lines.append(
        "Results are conditional on the chosen grid and evaluation period. BH correction applied to the 16-variant liqshock grid only (case-study mode). "
        "Replication: use the same run_id and deterministic seed for RC."
    )
    lines.append("")

    return "\n".join(lines)
