#!/usr/bin/env python3
"""
Milestone 4 research report: orthogonalized signals, advanced portfolio,
deflated Sharpe, PBO proxy, regime-conditioned metrics, lead/lag.
Research-only. Does not replace research_report.py.
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
from crypto_analyzer.experiments import log_experiment, load_experiments, record_experiment_run
from crypto_analyzer.factors import build_factor_matrix, rolling_multifactor_ols
from crypto_analyzer.integrity import assert_monotonic_time_index, assert_no_negative_or_zero_prices, validate_alignment, count_non_positive_prices, bad_row_rate
from crypto_analyzer.artifacts import ensure_dir, snapshot_outputs, write_json, timestamped_filename, compute_file_sha256
from crypto_analyzer.governance import make_run_manifest, save_manifest, get_git_commit, get_env_fingerprint, now_utc_iso, stable_run_id
from crypto_analyzer.diagnostics import build_health_summary, rolling_ic_stability

MIN_ASSETS = 3
DEFAULT_TOP_K = 3
DEFAULT_BOTTOM_K = 3
DISPERSION_WINDOW = 24


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "*No data*"
    return df.to_string(index=False)


def main() -> int:
    import sys
    if sys.prefix == sys.base_prefix:
        print("Not running inside venv. Use .\\scripts\\run.ps1 reportv2 or .\\.venv\\Scripts\\python.exe ...", flush=True)
    ap = argparse.ArgumentParser(description="M4 research report: signals hygiene, advanced portfolio, deflated Sharpe, PBO, regime")
    ap.add_argument("--freq", default="1h")
    ap.add_argument("--signals", default="clean_momentum,value_vs_beta", help="Comma-separated signal names")
    ap.add_argument("--portfolio", choices=["simple", "advanced", "qp_ls"], default="advanced")
    ap.add_argument("--cov-method", choices=["ewma", "lw", "shrink"], default="ewma")
    ap.add_argument("--n-trials", type=int, default=50, help="For deflated Sharpe")
    ap.add_argument("--out-dir", default="reports")
    ap.add_argument("--run-name", default=None, help="Run name for manifest (default: research_report_v2)")
    ap.add_argument("--notes", default="")
    ap.add_argument("--save-manifest", action="store_true", default=True)
    ap.add_argument("--no-save-manifest", dest="save_manifest", action="store_false")
    ap.add_argument("--save-charts", action="store_true")
    ap.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    ap.add_argument("--bottom-k", type=int, default=DEFAULT_BOTTOM_K)
    ap.add_argument("--fee-bps", type=float, default=30)
    ap.add_argument("--slippage-bps", type=float, default=10)
    ap.add_argument("--db", default=None)
    ap.add_argument("--strict-integrity", dest="strict_integrity", action="store_true", help="Exit 4 if bad row rate exceeds threshold")
    ap.add_argument("--strict-integrity-pct", dest="strict_integrity_pct", type=float, default=5.0, help="Max allowed bad row %% (default 5); used with --strict-integrity")
    ap.add_argument("--hypothesis", default=None, help="Hypothesis text for experiment registry")
    ap.add_argument("--tags", default=None, help="Comma-separated tags for experiment registry")
    ap.add_argument("--dataset-id", default=None, help="Dataset identifier for experiment registry")
    args = ap.parse_args()

    db = args.db or (db_path() if callable(db_path) else db_path())
    out_dir = Path(args.out_dir)
    ensure_dir(out_dir)
    for sub in ("csv", "charts", "manifests", "health"):
        ensure_dir(out_dir / sub)

    # Integrity diagnostic: non-positive price counts per table/column (informative; loaders filter at read time)
    try:
        from crypto_analyzer.config import price_column
        price_col = price_column() if callable(price_column) else "dex_price_usd"
    except Exception:
        price_col = "dex_price_usd"
    bars_table = f"bars_{args.freq.replace(' ', '')}"
    checks = [
        ("spot_price_snapshots", "spot_price_usd"),
        ("sol_monitor_snapshots", price_col),
        (bars_table, "close"),
    ]
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
    factor_ret = get_factor_returns(returns_df, meta_dict, db_path_override=db, freq=args.freq) if meta_dict else None

    lines = [
        "# Research Report v2 (Milestone 4)",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Freq: {args.freq}  Signals: {args.signals}  Portfolio: {args.portfolio}  Cov: {args.cov_method}",
        "",
        "## Assumptions",
        "| Parameter | Value |",
        "|-----------|-------|",
        f"| freq | {args.freq} |",
        f"| fee_bps | {getattr(args, 'fee_bps', 30)} |",
        f"| slippage_bps | {getattr(args, 'slippage_bps', 10)} |",
        f"| cost model | fee + slippage (bps) |",
        f"| cov_method | {args.cov_method} |",
        f"| portfolio | {args.portfolio} |",
        f"| deflated_sharpe n_trials | {getattr(args, 'n_trials', 50)} |",
        "",
        "## 1) Universe",
    ]
    if n_assets < 1:
        lines.append("No assets. Add DEX pairs or ensure DB path is correct.")
        report_path = out_dir / timestamped_filename("research_v2", "md", sep="_")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"Report: {report_path}")
        return 0

    # Integrity checks (warnings only)
    df_for_ts = returns_df.reset_index()
    ts_col = "ts_utc" if "ts_utc" in df_for_ts.columns else df_for_ts.columns[0]
    warn_mono = assert_monotonic_time_index(df_for_ts, col=ts_col)
    if warn_mono:
        print("Integrity warning:", warn_mono)
    warn_prices = assert_no_negative_or_zero_prices(returns_df)
    if warn_prices:
        print("Integrity warning:", warn_prices)

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

    report_path = out_dir / timestamped_filename("research_v2", "md", sep="_")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Report: {report_path}")

    output_paths = [str(report_path)]

    # Research Health Summary + health_summary.json
    health_dir = out_dir / "health"
    try:
        data_coverage = {"n_assets": n_assets, "n_bars": len(returns_df)}
        signal_stability = {}
        if len(signals_dict) >= 1 and not returns_df.empty:
            sig_first = next(iter(signals_dict.values()))
            if sig_first is not None and not sig_first.empty:
                from crypto_analyzer.alpha_research import information_coefficient
                fwd1 = compute_forward_returns(returns_df, 1)
                ic_ts = information_coefficient(sig_first, fwd1, method="spearman")
                signal_stability = rolling_ic_stability(ic_ts, window=min(24, max(2, len(ic_ts) // 2)))
        overfitting_risk = {}
        if portfolio_pnls:
            for name, pnl in portfolio_pnls.items():
                if len(pnl) >= 10 and pnl.std() and pnl.std() > 0:
                    overfitting_risk[f"sharpe_{name}"] = float(pnl.mean() / pnl.std())
        health = build_health_summary(
            data_coverage=data_coverage,
            signal_stability=signal_stability if signal_stability else None,
            overfitting_risk_proxies=overfitting_risk if overfitting_risk else None,
        )
        health_path = health_dir / "health_summary.json"
        write_json(health, health_path)
        output_paths.append(str(health_path))
    except Exception as e:
        print("Health summary skip:", e)

    # ---- Multi-factor OLS summary metrics ----
    mf_metrics: dict = {}
    try:
        factor_matrix = build_factor_matrix(returns_df)
        if not factor_matrix.empty:
            betas_dict, r2_mf, resid_mf = rolling_multifactor_ols(
                returns_df, factor_matrix, window=72, min_obs=24
            )
            if "BTC_spot" in betas_dict and not betas_dict["BTC_spot"].empty:
                mf_metrics["beta_btc_mean"] = float(betas_dict["BTC_spot"].mean(skipna=True).mean())
            if "ETH_spot" in betas_dict and not betas_dict["ETH_spot"].empty:
                mf_metrics["beta_eth_mean"] = float(betas_dict["ETH_spot"].mean(skipna=True).mean())
            if not r2_mf.empty:
                mf_metrics["r2_mean"] = float(r2_mf.mean(skipna=True).mean())
    except Exception as e:
        print("Multi-factor OLS skip:", e)

    # Experiment log (legacy JSON/CSV)
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

    if getattr(args, "save_manifest", True):
        try:
            data_window = {
                "start_ts": str(returns_df.index.min()) if not returns_df.empty else "",
                "end_ts": str(returns_df.index.max()) if not returns_df.empty else "",
                "freq": args.freq,
                "n_assets": n_assets,
                "bars_per_asset_summary": int(returns_df.shape[0]) if not returns_df.empty else 0,
            }
            metrics_summary = {k: float(v.mean() / v.std()) if v.std() and v.std() > 0 else np.nan for k, v in portfolio_pnls.items()}
            outputs_with_hashes = snapshot_outputs(output_paths)
            manifest = make_run_manifest(
                name=getattr(args, "run_name", None) or "research_report_v2",
                args={"freq": args.freq, "signals": args.signals, "portfolio": args.portfolio, "cov_method": args.cov_method},
                data_window=data_window,
                outputs=outputs_with_hashes,
                metrics=metrics_summary,
                notes=getattr(args, "notes", "") or "",
            )
            save_manifest(str(out_dir), manifest)
        except Exception as e:
            print("Manifest skip:", e)

    # ---- SQLite experiment registry ----
    try:
        from crypto_analyzer.spec import RESEARCH_SPEC_VERSION
        import hashlib as _hl, json as _js

        pnl_sharpes = {k: float(v.mean() / v.std()) if v.std() and v.std() > 0 else float("nan") for k, v in portfolio_pnls.items()}
        canonical_metrics: dict = {
            "universe_size": float(n_assets),
        }
        if pnl_sharpes:
            canonical_metrics["sharpe"] = float(np.nanmean(list(pnl_sharpes.values())))
        for k, v in pnl_sharpes.items():
            canonical_metrics[f"sharpe_{k}"] = v

        if portfolio_pnls:
            for k, pnl in portfolio_pnls.items():
                eq = (1 + pnl).cumprod()
                dd = (eq.cummax() - eq) / eq.cummax()
                canonical_metrics[f"max_drawdown_{k}"] = float(dd.max()) if not dd.empty else float("nan")
            canonical_metrics["max_drawdown"] = float(np.nanmax([canonical_metrics.get(f"max_drawdown_{k}", float("nan")) for k in portfolio_pnls]))

        if signals_dict:
            fwd1 = compute_forward_returns(returns_df, 1)
            for sname, sig in signals_dict.items():
                ic_ts = information_coefficient(sig, fwd1, method="spearman")
                if not ic_ts.empty and ic_ts.notna().any():
                    canonical_metrics[f"mean_ic_{sname}"] = float(ic_ts.mean())
            ic_vals = [canonical_metrics[k] for k in canonical_metrics if k.startswith("mean_ic_")]
            if ic_vals:
                canonical_metrics["mean_ic"] = float(np.nanmean(ic_vals))

        if portfolio_pnls:
            turnover_vals = []
            for k in portfolio_pnls:
                sig = signals_dict.get(k) or (orth_dict.get(k) if orth_dict else None)
                if sig is not None and not sig.empty:
                    r = rank_signal_df(sig)
                    w = long_short_from_ranks(r, args.top_k, args.bottom_k, gross_leverage=1.0)
                    t = turnover_from_weights(w)
                    turnover_vals.append(float(t.mean()))
            if turnover_vals:
                canonical_metrics["turnover"] = float(np.nanmean(turnover_vals))

        canonical_metrics.update(mf_metrics)

        config_blob = _js.dumps({"freq": args.freq, "signals": args.signals, "portfolio": args.portfolio, "cov_method": args.cov_method}, sort_keys=True)
        config_hash = _hl.sha256(config_blob.encode()).hexdigest()[:16]
        env_fp = str(get_env_fingerprint())

        ts_now = now_utc_iso()
        run_payload = {"name": "research_report_v2", "ts_utc": ts_now, "config_hash": config_hash}
        run_id = stable_run_id(run_payload)

        experiment_db_path = os.environ.get("EXPERIMENT_DB_PATH", str(out_dir / "experiments.db"))
        from crypto_analyzer.experiments import parse_tags
        tags_list = parse_tags(args.tags) if getattr(args, "tags", None) else []
        params_dict = {"freq": args.freq, "signals": args.signals, "portfolio": args.portfolio, "cov_method": args.cov_method}
        experiment_row = {
            "run_id": run_id,
            "ts_utc": ts_now,
            "git_commit": get_git_commit(),
            "spec_version": RESEARCH_SPEC_VERSION,
            "out_dir": str(out_dir),
            "notes": getattr(args, "notes", "") or "",
            "data_start": str(returns_df.index.min()) if not returns_df.empty else "",
            "data_end": str(returns_df.index.max()) if not returns_df.empty else "",
            "config_hash": config_hash,
            "env_fingerprint": env_fp,
            "hypothesis": getattr(args, "hypothesis", None) or "",
            "tags": tags_list,
            "dataset_id": getattr(args, "dataset_id", None) or "",
            "params": params_dict,
        }

        artifacts_for_db = [
            {"artifact_path": p, "sha256": compute_file_sha256(p)}
            for p in output_paths
        ]

        record_experiment_run(
            db_path=experiment_db_path,
            experiment_row=experiment_row,
            metrics_dict=canonical_metrics,
            artifacts_list=artifacts_for_db,
        )
        print(f"Experiment recorded: {run_id} -> {experiment_db_path}")
    except Exception as e:
        print("SQLite experiment registry skip:", e)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
