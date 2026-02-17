#!/usr/bin/env python3
"""
Milestone 4 research report: orthogonalized signals, advanced portfolio,
deflated Sharpe, PBO proxy, regime-conditioned metrics, lead/lag.
Research-only. Does not replace research_report.py.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from crypto_analyzer.config import db_path
from crypto_analyzer.research_universe import get_research_assets
from crypto_analyzer.data import get_factor_returns
from crypto_analyzer.alpha_research import (
    compute_forward_returns,
    information_coefficient,
    ic_summary,
    rank_signal_df,
    signal_momentum_24h,
    signal_residual_momentum_24h,
    compute_dispersion_series,
    dispersion_zscore_series,
)
from crypto_analyzer.signals_xs import (
    zscore_cross_section,
    orthogonalize_signals,
    build_exposure_panel,
    value_vs_beta,
    clean_momentum,
)
from crypto_analyzer.portfolio import (
    long_short_from_ranks,
    portfolio_returns_from_weights,
    turnover_from_weights,
    apply_costs_to_portfolio,
)
from crypto_analyzer.portfolio_advanced import optimize_long_short_portfolio
from crypto_analyzer.risk_model import estimate_covariance
from crypto_analyzer.evaluation import conditional_metrics, stability_report, lead_lag_analysis
from crypto_analyzer.multiple_testing import deflated_sharpe_ratio, reality_check_warning, pbo_proxy_walkforward
from crypto_analyzer.experiments import log_experiment, load_experiments

MIN_ASSETS = 3
DEFAULT_TOP_K = 3
DEFAULT_BOTTOM_K = 3
DISPERSION_WINDOW = 24


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "*No data*"
    return df.to_string(index=False)


def main() -> int:
    ap = argparse.ArgumentParser(description="M4 research report: signals hygiene, advanced portfolio, deflated Sharpe, PBO, regime")
    ap.add_argument("--freq", default="1h")
    ap.add_argument("--signals", default="clean_momentum,value_vs_beta", help="Comma-separated signal names")
    ap.add_argument("--portfolio", choices=["simple", "advanced"], default="advanced")
    ap.add_argument("--cov-method", choices=["ewma", "lw", "shrink"], default="ewma")
    ap.add_argument("--n-trials", type=int, default=50, help="For deflated Sharpe")
    ap.add_argument("--out-dir", default="reports")
    ap.add_argument("--save-charts", action="store_true")
    ap.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    ap.add_argument("--bottom-k", type=int, default=DEFAULT_BOTTOM_K)
    ap.add_argument("--fee-bps", type=float, default=30)
    ap.add_argument("--slippage-bps", type=float, default=10)
    ap.add_argument("--db", default=None)
    args = ap.parse_args()

    db = args.db or (db_path() if callable(db_path) else db_path())
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    returns_df, meta_df = get_research_assets(db, args.freq, include_spot=True)
    n_assets = returns_df.shape[1] if not returns_df.empty else 0
    meta_dict = meta_df.set_index("asset_id")["label"].to_dict() if not meta_df.empty else {}
    factor_ret = get_factor_returns(returns_df, meta_dict, db_path_override=db, freq=args.freq) if meta_dict else None

    lines = [
        "# Research Report v2 (Milestone 4)",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Freq: {args.freq}  Signals: {args.signals}  Portfolio: {args.portfolio}  Cov: {args.cov_method}",
        "",
        "## 1) Universe",
    ]
    if n_assets < 1:
        lines.append("No assets. Add DEX pairs or ensure DB path is correct.")
        report_path = out_dir / f"research_report_v2_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"Report: {report_path}")
        return 0

    lines.append(f"Assets: {n_assets}  Bars: {len(returns_df)}")
    lines.append("")

    # Build signals (including institutional composites)
    sig_mom = signal_momentum_24h(returns_df, args.freq) if n_assets >= 1 else pd.DataFrame()
    sig_clean = clean_momentum(returns_df, args.freq, factor_ret) if not returns_df.empty else pd.DataFrame()
    sig_value = value_vs_beta(returns_df, args.freq, factor_ret) if not returns_df.empty else None
    if sig_value is not None and sig_value.empty:
        sig_value = None

    signal_names = [s.strip() for s in args.signals.split(",") if s.strip()]
    signals_dict = {}
    if "clean_momentum" in signal_names and not sig_clean.empty:
        signals_dict["clean_momentum"] = sig_clean
    if "value_vs_beta" in signal_names and sig_value is not None and not sig_value.empty:
        signals_dict["value_vs_beta"] = sig_value
    if "momentum_24h" in signal_names and not sig_mom.empty:
        signals_dict["momentum_24h"] = sig_mom

    # ---- Orthogonalized signals section ----
    lines.append("## 2) Orthogonalized signals")
    if len(signals_dict) >= 2:
        orth_dict, report = orthogonalize_signals(signals_dict)
        if report:
            lines.append("Cross-correlation report (avg abs corr before/after):")
            for k, v in report.items():
                lines.append(f"- {k}: {v:.4f}")
            lines.append("")
        if orth_dict:
            lines.append("Orthogonalized keys: " + ", ".join(orth_dict.keys()))
    else:
        lines.append("*Need at least 2 signals for orthogonalization.*")
        orth_dict = dict(signals_dict)
    lines.append("")

    # ---- Portfolio section (simple or advanced) ----
    lines.append("## 3) Portfolio (research-only)")
    lines.append(f"Mode: {args.portfolio}. Fee: {args.fee_bps} bps, Slippage: {args.slippage_bps} bps.")
    lines.append("")

    portfolio_pnls = {}
    walk_forward_rows = []

    for name, sig_df in (orth_dict or signals_dict).items():
        if sig_df is None or sig_df.empty:
            continue
        ranks = rank_signal_df(sig_df)
        from crypto_analyzer.portfolio import long_short_from_ranks
        weights_df = long_short_from_ranks(ranks, args.top_k, args.bottom_k, gross_leverage=1.0)
        if args.portfolio == "advanced" and n_assets >= MIN_ASSETS:
            last_t = ranks.index[-1] if len(ranks) else None
            if last_t is not None:
                er = ranks.loc[last_t].astype(float)
                window = returns_df.tail(72) if len(returns_df) >= 72 else returns_df
                cov = estimate_covariance(window, method=args.cov_method, halflife=24.0)
                constraints = {"dollar_neutral": True, "target_gross_leverage": 1.0, "max_weight_per_asset": 0.25}
                if factor_ret is not None:
                    exp = build_exposure_panel(returns_df, meta_df, factor_returns=factor_ret, freq=args.freq)
                    if "beta_btc_72" in exp and not exp["beta_btc_72"].empty:
                        b = exp["beta_btc_72"].loc[last_t] if last_t in exp["beta_btc_72"].index else exp["beta_btc_72"].iloc[-1]
                        constraints["betas"] = b
                w, diag = optimize_long_short_portfolio(er, cov, constraints)
                if not w.empty:
                    lines.append(f"### {name} (advanced diagnostics)")
                    lines.append(f"Beta: {diag.get('achieved_beta', np.nan):.4f}  Gross: {diag.get('gross_leverage', 0):.4f}  Net: {diag.get('net_exposure', 0):.4f}  N_assets: {diag.get('n_assets', 0)}")
                    lines.append("")

        if weights_df.empty:
            continue
        port_ret = portfolio_returns_from_weights(weights_df, returns_df)
        if port_ret.dropna().empty:
            continue
        turnover_ser = turnover_from_weights(weights_df)
        port_ret_net = apply_costs_to_portfolio(port_ret, turnover_ser, args.fee_bps, args.slippage_bps)
        port_ret_net = port_ret_net.dropna()
        portfolio_pnls[name] = port_ret_net
        if len(port_ret_net) >= 2:
            walk_forward_rows.append({"strategy": name, "train_sharpe": np.nan, "test_sharpe": float(port_ret_net.mean() / port_ret_net.std()) if port_ret_net.std() and port_ret_net.std() > 0 else np.nan})

    # ---- Deflated Sharpe ----
    lines.append("## 4) Overfitting defenses")
    lines.append(f"Deflated Sharpe (n_trials={args.n_trials}):")
    for name, pnl in portfolio_pnls.items():
        if len(pnl) < 10:
            continue
        dsr = deflated_sharpe_ratio(pnl, args.freq, args.n_trials, skew_kurtosis_optional=True)
        lines.append(f"- **{name}**: raw_sr={dsr.get('raw_sr', np.nan):.4f}  deflated_sr={dsr.get('deflated_sr', np.nan):.4f}")
    wf_df = pd.DataFrame(walk_forward_rows) if walk_forward_rows else pd.DataFrame()
    pbo = pbo_proxy_walkforward(wf_df)
    lines.append(f"PBO proxy: {pbo.get('pbo_proxy', np.nan)}  ({pbo.get('explanation', '')})")
    lines.append(reality_check_warning(len(signals_dict), len(portfolio_pnls)))
    lines.append("")

    # ---- Regime-conditioned ----
    lines.append("## 5) Regime-conditioned performance")
    disp_series = compute_dispersion_series(returns_df) if not returns_df.empty else pd.Series(dtype=float)
    disp_z = dispersion_zscore_series(disp_series, DISPERSION_WINDOW) if len(disp_series) >= DISPERSION_WINDOW else pd.Series(dtype=float)
    regime_series = pd.Series(index=returns_df.index, dtype=str)
    if not disp_z.empty:
        regime_series = disp_z.apply(lambda z: "high_disp" if z > 1 else ("low_disp" if z < -1 else "mid"))
    for name, pnl in portfolio_pnls.items():
        if pnl.empty or regime_series.empty:
            continue
        cm = conditional_metrics(pnl, regime_series)
        if not cm.empty:
            lines.append(f"### {name}")
            lines.append(_table(cm.round(4)))
            lines.append("")

    # ---- Lead/lag (optional) ----
    lines.append("## 6) Lead/lag (signal vs return)")
    if len(signals_dict) >= 1 and not returns_df.empty and n_assets >= 1:
        sig_first = next(iter(signals_dict.values()))
        ll = lead_lag_analysis(sig_first, returns_df, lags=list(range(-12, 13)))
        if not ll.empty:
            lines.append("Lags -12..+12 (1h): sample correlations")
            lines.append(ll.round(4).to_string())
            if args.save_charts and out_dir:
                try:
                    import matplotlib
                    matplotlib.use("Agg")
                    import matplotlib.pyplot as plt
                    fig, ax = plt.subplots(1, 1)
                    ll.plot(ax=ax)
                    ax.set_xlabel("Lag (bars)")
                    ax.set_ylabel("Correlation")
                    ax.set_title("Lead/lag: signal vs return")
                    plt.tight_layout()
                    plt.savefig(out_dir / "research_v2_leadlag.png", dpi=150)
                    plt.close()
                    print("Lead/lag chart saved.")
                except Exception as e:
                    print("Lead/lag chart skip:", e)
    else:
        lines.append("*Insufficient data for lead/lag.*")
    lines.append("")

    report_path = out_dir / f"research_report_v2_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Report: {report_path}")

    # Experiment log
    try:
        log_experiment(
            run_name=f"research_v2_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}",
            config_dict={"freq": args.freq, "signals": args.signals, "portfolio": args.portfolio, "cov_method": args.cov_method},
            metrics_dict={k: float(v.mean() / v.std()) if v.std() and v.std() > 0 else np.nan for k, v in portfolio_pnls.items()},
            artifacts_paths=[str(report_path)],
            out_dir=str(out_dir / "experiments"),
        )
    except Exception as e:
        print("Experiment log skip:", e)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
