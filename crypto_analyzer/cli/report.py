#!/usr/bin/env python3
"""
Research report: universe, IC summary, IC decay, portfolio backtest, regime conditioning.
Research-only; no execution. Requires >= 3 assets for cross-sectional analysis.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from crypto_analyzer.alpha_research import (
    compute_dispersion_series,
    compute_forward_returns,
    dispersion_zscore_series,
    ic_decay,
    ic_summary,
    information_coefficient,
    rank_signal_df,
    signal_beta_compression,
    signal_dispersion_conditioned,
    signal_momentum_24h,
    signal_residual_momentum_24h,
)
from crypto_analyzer.artifacts import ensure_dir, snapshot_outputs, timestamped_filename
from crypto_analyzer.config import db_path
from crypto_analyzer.data import get_factor_returns
from crypto_analyzer.governance import make_run_manifest, save_manifest
from crypto_analyzer.integrity import (
    assert_monotonic_time_index,
    assert_no_negative_or_zero_prices,
    bad_row_rate,
    count_non_positive_prices,
    validate_alignment,
)
from crypto_analyzer.portfolio import (
    apply_costs_to_portfolio,
    long_short_from_ranks,
    portfolio_returns_from_weights,
    turnover_from_weights,
)
from crypto_analyzer.research_universe import get_research_assets
from crypto_analyzer.statistics import reality_check_simple, significance_summary

MIN_ASSETS = 3
DEFAULT_TOP_K = 3
DEFAULT_BOTTOM_K = 3
DEFAULT_HORIZONS = [1, 2, 3, 6, 12, 24]
DISPERSION_WINDOW = 24


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "*No data*"
    return df.to_string(index=False)


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if sys.prefix == sys.base_prefix:
        print(
            "Not running inside venv. Use .\\scripts\\run.ps1 report or .\\.venv\\Scripts\\python.exe ...", flush=True
        )
    ap = argparse.ArgumentParser(description="Research report: IC, decay, portfolio, regime")
    ap.add_argument("--freq", default="1h")
    ap.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    ap.add_argument("--bottom-k", type=int, default=DEFAULT_BOTTOM_K)
    ap.add_argument("--horizons", default=",".join(map(str, DEFAULT_HORIZONS)), help="Comma-separated horizon bars")
    ap.add_argument("--fee-bps", type=float, default=30)
    ap.add_argument("--slippage-bps", type=float, default=10)
    ap.add_argument("--out-dir", default="reports")
    ap.add_argument("--run-name", default=None, help="Run name for manifest (default: research_report)")
    ap.add_argument("--notes", default="")
    ap.add_argument("--save-manifest", action="store_true", default=True, help="Write run manifest (default: True)")
    ap.add_argument("--no-save-manifest", dest="save_manifest", action="store_false")
    ap.add_argument("--db", default=None)
    ap.add_argument("--save-charts", action="store_true")
    ap.add_argument(
        "--strict-integrity",
        dest="strict_integrity",
        action="store_true",
        help="Exit 4 if bad row rate exceeds threshold",
    )
    ap.add_argument(
        "--strict-integrity-pct",
        dest="strict_integrity_pct",
        type=float,
        default=5.0,
        help="Max allowed bad row %% (default 5); used with --strict-integrity",
    )
    args = ap.parse_args(argv)

    db = args.db or (db_path() if callable(db_path) else db_path())
    out_dir = Path(args.out_dir)
    ensure_dir(out_dir)
    for sub in ("csv", "charts", "manifests"):
        ensure_dir(out_dir / sub)

    horizons = [int(x.strip()) for x in args.horizons.split(",") if x.strip()]
    if not horizons:
        horizons = DEFAULT_HORIZONS

    # Integrity diagnostic: non-positive price counts per table/column
    try:
        from crypto_analyzer.config import price_column

        price_col = price_column() if callable(price_column) else "dex_price_usd"
    except Exception:
        price_col = "dex_price_usd"
    bars_table = f"bars_{args.freq.replace(' ', '')}"
    checks = [("spot_price_snapshots", "spot_price_usd"), ("sol_monitor_snapshots", price_col), (bars_table, "close")]
    for table, col, count in count_non_positive_prices(db, checks):
        print(f"Integrity: {table}.{col}: {count} non-positive (dropped at load time)")
    if getattr(args, "strict_integrity", False):
        pct_limit = float(getattr(args, "strict_integrity_pct", 5.0))
        for table, col, bad, total, pct in bad_row_rate(db, checks):
            if total and pct > pct_limit:
                print(f"Integrity FAIL: {table}.{col} bad rate {pct:.2f}% (>{pct_limit}%)")
                return 4
        print("Integrity: strict check passed (bad row rate within limit)")

    returns_df, meta_df = get_research_assets(db, args.freq, include_spot=True)
    n_assets = returns_df.shape[1] if not returns_df.empty else 0
    meta_dict = meta_df.set_index("asset_id")["label"].to_dict() if not meta_df.empty else {}

    lines = [
        "# Research Report",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Freq: {args.freq}",
        "",
        "## 1) Universe summary",
    ]

    if n_assets < MIN_ASSETS:
        lines.append(
            f"**Need >= {MIN_ASSETS} assets for cross-sectional research.** Current: {n_assets}. Add more DEX pairs or ensure spot series exist."
        )
        lines.append("")
        report_path = out_dir / timestamped_filename("research_report", "md", sep="_")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"Report: {report_path}")
        return 0

    # Integrity checks (warnings only)
    warn_mono = assert_monotonic_time_index(returns_df.reset_index(), col="ts_utc")
    if warn_mono:
        print("Integrity warning:", warn_mono)
    warn_prices = assert_no_negative_or_zero_prices(returns_df)
    if warn_prices:
        print("Integrity warning:", warn_prices)
    for _ in validate_alignment(returns_df, pd.DataFrame(), horizons):
        print("Integrity warning: alignment")

    lines.append(f"Assets: {n_assets}")
    lines.append(f"Bars: {len(returns_df)}")
    lines.append("")
    lines.append(_table(meta_df))
    lines.append("")

    # Factor returns for beta_compression and residual
    factor_ret = get_factor_returns(returns_df, meta_dict, db_path_override=db, freq=args.freq) if meta_dict else None

    # Signals
    sig_mom = signal_momentum_24h(returns_df, args.freq)
    sig_resid = signal_residual_momentum_24h(returns_df, args.freq)
    sig_beta = signal_beta_compression(returns_df, factor_ret) if factor_ret is not None else pd.DataFrame()
    disp_series = compute_dispersion_series(returns_df)
    disp_z = (
        dispersion_zscore_series(disp_series, DISPERSION_WINDOW)
        if len(disp_series) >= DISPERSION_WINDOW
        else pd.Series(dtype=float)
    )
    sig_disp = (
        signal_dispersion_conditioned(sig_mom, disp_z) if not sig_mom.empty and not disp_z.empty else pd.DataFrame()
    )

    signals_to_report = [
        ("momentum_24h", sig_mom),
        ("residual_momentum_24h", sig_resid),
        ("beta_compression", sig_beta),
        ("dispersion_conditioned_momentum", sig_disp),
    ]

    lines.append("## 2) Signal IC summary")
    lines.append("(mean IC, t-stat, hit rate, 95% CI, n_obs)")
    lines.append("")

    ic_results = {}
    for name, sig_df in signals_to_report:
        if sig_df is None or sig_df.empty:
            continue
        ranks = rank_signal_df(sig_df)
        fwd = compute_forward_returns(returns_df, horizon_bars=horizons[0] if horizons else 1)
        ic_ts = information_coefficient(sig_df, fwd, method="spearman")
        s = ic_summary(ic_ts)
        ic_results[name] = s
        lines.append(f"### {name}")
        lines.append(_table(pd.DataFrame([s])))
        lines.append("")

    lines.append("## 3) IC decay (mean IC vs horizon)")
    for name, sig_df in signals_to_report:
        if sig_df is None or sig_df.empty:
            continue
        decay_df = ic_decay(sig_df, returns_df, horizons, method="spearman")
        if not decay_df.empty:
            lines.append(f"### {name}")
            lines.append(_table(decay_df.round(4)))
            lines.append("")
    lines.append("")

    # 4) Portfolio backtest
    lines.append("## 4) Portfolio backtest (research-only)")
    lines.append(
        f"Long/short: top {args.top_k} / bottom {args.bottom_k}. Fee: {args.fee_bps} bps, Slippage: {args.slippage_bps} bps."
    )
    lines.append("")

    for name, sig_df in signals_to_report:
        if sig_df is None or sig_df.empty:
            continue
        if name == "beta_compression" and sig_df.empty:
            continue
        ranks = rank_signal_df(sig_df)
        weights_df = long_short_from_ranks(ranks, args.top_k, args.bottom_k, gross_leverage=1.0)
        if weights_df.empty:
            continue
        port_ret = portfolio_returns_from_weights(weights_df, returns_df)
        turnover_ser = turnover_from_weights(weights_df)
        port_ret_net = apply_costs_to_portfolio(port_ret, turnover_ser, args.fee_bps, args.slippage_bps)
        port_ret_net = port_ret_net.dropna()
        if len(port_ret_net) < 2:
            continue
        gross_ret = (1 + port_ret).dropna()
        gross_total = float(gross_ret.prod() - 1.0) if len(gross_ret) else np.nan
        net_total = float((1 + port_ret_net).prod() - 1.0) if len(port_ret_net) else np.nan
        cost_drag = (gross_total - net_total) * 100 if pd.notna(gross_total) and pd.notna(net_total) else 0
        summ = significance_summary(port_ret_net, args.freq)
        eq = (1 + port_ret_net).cumprod()
        dd = eq.cummax() - eq
        max_dd = float(dd.max()) if len(dd) else np.nan
        avg_turnover = float(turnover_ser.mean()) if turnover_ser.notna().any() else 0
        lines.append(f"### {name}")
        lines.append(
            f"Gross total return: {gross_total:.4f}  |  Net total return: {net_total:.4f}  |  Cost drag %: {cost_drag:.2f}"
        )
        lines.append(
            f"Sharpe (net): {summ['sharpe_annual']:.4f}  |  95% CI: [{summ['sharpe_ci_95_lo']:.4f}, {summ['sharpe_ci_95_hi']:.4f}]"
        )
        lines.append(f"Max drawdown: {max_dd:.4f}  |  Avg turnover: {avg_turnover:.4f}")
        lines.append("")

    # 5) Regime-conditioned (simplified: split by dispersion z)
    lines.append("## 5) Regime-conditioned performance")
    if not sig_mom.empty and not disp_z.empty:
        ranks = rank_signal_df(sig_mom)
        weights_df = long_short_from_ranks(ranks, args.top_k, args.bottom_k, gross_leverage=1.0)
        port_ret = portfolio_returns_from_weights(weights_df, returns_df).dropna()
        common = port_ret.index.intersection(disp_z.index)
        if len(common) >= 10:
            port_ret = port_ret.loc[common]
            disp_z_a = disp_z.reindex(common).ffill().bfill()
            high = (disp_z_a > 1).reindex(port_ret.index).fillna(False)
            low = (disp_z_a < -1).reindex(port_ret.index).fillna(False)
            mid = (~high & ~low).reindex(port_ret.index).fillna(False)
            rows = []
            for label, mask in [("z > +1 (high disp)", high), ("z in [-1, +1]", mid), ("z < -1 (low disp)", low)]:
                r = port_ret.loc[mask]
                if len(r) >= 2 and r.std() and r.std() != 0:
                    from crypto_analyzer.features import bars_per_year

                    sh = r.mean() / r.std() * np.sqrt(bars_per_year(args.freq))
                    rows.append({"regime": label, "n_bars": len(r), "mean_ret": r.mean(), "sharpe_approx": sh})
            if rows:
                lines.append(_table(pd.DataFrame(rows).round(4)))
        else:
            lines.append("*Insufficient overlap for regime split.*")
    else:
        lines.append("*Need momentum signal and dispersion z.*")
    lines.append("")

    warn = reality_check_simple(ic_results, threshold=10)
    if warn:
        lines.append("---")
        lines.append(f"**Note:** {warn}")
        lines.append("")

    report_path = out_dir / timestamped_filename("research_report", "md", sep="_")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Report: {report_path}")

    output_paths = [str(report_path)]
    csv_dir = out_dir / "csv"
    if ic_results:
        p = csv_dir / "research_ic_summary.csv"
        pd.DataFrame(ic_results).T.to_csv(p, index=True)
        output_paths.append(str(p))
    for name, sig_df in signals_to_report:
        if sig_df is not None and not sig_df.empty:
            decay_df = ic_decay(sig_df, returns_df, horizons, method="spearman")
            if not decay_df.empty:
                p = csv_dir / f"research_ic_decay_{name}.csv"
                decay_df.to_csv(p, index=False)
                output_paths.append(str(p))

    charts_dir = out_dir / "charts"
    if args.save_charts and n_assets >= MIN_ASSETS and not sig_mom.empty:
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fwd1 = compute_forward_returns(returns_df, 1)
            ic_ts = information_coefficient(sig_mom, fwd1, method="spearman")
            if not ic_ts.empty and ic_ts.notna().any():
                fig, ax = plt.subplots(1, 1)
                ic_ts.dropna().plot(ax=ax)
                ax.set_title("IC (momentum_24h vs fwd 1-bar)")
                ax.set_ylabel("IC")
                plt.tight_layout()
                p = charts_dir / "research_ic_series.png"
                plt.savefig(p, dpi=150)
                output_paths.append(str(p))
                plt.close()
            decay_chart = ic_decay(sig_mom, returns_df, horizons, method="spearman")
            if not decay_chart.empty:
                fig, ax = plt.subplots(1, 1)
                ax.plot(decay_chart["horizon_bars"], decay_chart["mean_ic"], marker="o")
                ax.set_xlabel("Horizon (bars)")
                ax.set_ylabel("Mean IC")
                ax.set_title("IC decay (momentum_24h)")
                plt.tight_layout()
                p = charts_dir / "research_ic_decay.png"
                plt.savefig(p, dpi=150)
                output_paths.append(str(p))
                plt.close()
            print("Charts saved to", charts_dir)
        except Exception as e:
            print("Charts skip:", e)

    if getattr(args, "save_manifest", True):
        try:
            data_window = {
                "start_ts": str(returns_df.index.min()) if not returns_df.empty else "",
                "end_ts": str(returns_df.index.max()) if not returns_df.empty else "",
                "freq": args.freq,
                "n_assets": n_assets,
                "bars_per_asset_summary": int(returns_df.shape[0]) if not returns_df.empty else 0,
            }
            metrics_summary = {
                k: (v.get("mean_ic", np.nan) if isinstance(v, dict) else v) for k, v in (ic_results or {}).items()
            }
            outputs_with_hashes = snapshot_outputs(output_paths)
            manifest = make_run_manifest(
                name=getattr(args, "run_name", None) or "research_report",
                args={
                    "freq": args.freq,
                    "top_k": args.top_k,
                    "bottom_k": args.bottom_k,
                    "fee_bps": args.fee_bps,
                    "slippage_bps": args.slippage_bps,
                },
                data_window=data_window,
                outputs=outputs_with_hashes,
                metrics=metrics_summary,
                notes=getattr(args, "notes", "") or "",
            )
            save_manifest(str(out_dir), manifest)
        except Exception as e:
            print("Manifest skip:", e)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
