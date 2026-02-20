#!/usr/bin/env python3
"""
Milestone 4 research report: orthogonalized signals, advanced portfolio,
deflated Sharpe, PBO proxy, regime-conditioned metrics, lead/lag.
Research-only. Does not replace research_report.py.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crypto_analyzer.alpha_research import (
    compute_dispersion_series,
    compute_forward_returns,
    dispersion_zscore_series,
    ic_decay,
    ic_summary,
    information_coefficient,
    rank_signal_df,
    signal_momentum_24h,
)
from crypto_analyzer.artifacts import (
    compute_file_sha256,
    ensure_dir,
    snapshot_outputs,
    timestamped_filename,
    write_df_csv_stable,
    write_json,
    write_json_sorted,
)
from crypto_analyzer.config import db_path
from crypto_analyzer.data import get_factor_returns
from crypto_analyzer.dataset import compute_dataset_fingerprint, dataset_id_from_fingerprint, fingerprint_to_json
from crypto_analyzer.diagnostics import build_health_summary, rolling_ic_stability
from crypto_analyzer.evaluation import conditional_metrics, lead_lag_analysis
from crypto_analyzer.experiments import log_experiment, record_experiment_run
from crypto_analyzer.factors import build_factor_matrix, rolling_multifactor_ols
from crypto_analyzer.governance import (
    get_env_fingerprint,
    get_git_commit,
    make_run_manifest,
    now_utc_iso,
    save_manifest,
    stable_run_id,
)
from crypto_analyzer.integrity import (
    assert_monotonic_time_index,
    assert_no_negative_or_zero_prices,
    bad_row_rate,
    count_non_positive_prices,
)
from crypto_analyzer.multiple_testing import deflated_sharpe_ratio, pbo_proxy_walkforward, reality_check_warning
from crypto_analyzer.multiple_testing_adjuster import adjust as adjust_pvalues
from crypto_analyzer.portfolio import (
    apply_costs_to_portfolio,
    long_short_from_ranks,
    portfolio_returns_from_weights,
    turnover_from_weights,
)
from crypto_analyzer.portfolio_advanced import optimize_long_short_portfolio
from crypto_analyzer.research_universe import get_research_assets
from crypto_analyzer.risk_model import estimate_covariance
from crypto_analyzer.signals_xs import (
    build_exposure_panel,
    clean_momentum,
    orthogonalize_signals,
    value_vs_beta,
)
from crypto_analyzer.statistics import safe_nanmean
from crypto_analyzer.validation import (
    ic_decay_by_regime,
    ic_summary_by_regime_multi,
    regime_coverage,
)
from crypto_analyzer.validation_bundle import ValidationBundle

MIN_ASSETS = 3
VALIDATION_HORIZONS = [1, 4, 12]
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
        print(
            "Not running inside venv. Use .\\scripts\\run.ps1 reportv2 or .\\.venv\\Scripts\\python.exe ...", flush=True
        )
    ap = argparse.ArgumentParser(
        description="M4 research report: signals hygiene, advanced portfolio, deflated Sharpe, PBO, regime"
    )
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
    ap.add_argument("--hypothesis", default=None, help="Hypothesis text for experiment registry")
    ap.add_argument("--tags", default=None, help="Comma-separated tags for experiment registry")
    ap.add_argument("--dataset-id", default=None, help="Explicit dataset ID (overrides computed)")
    ap.add_argument(
        "--regimes",
        default=None,
        metavar="REGIME_RUN_ID",
        help="Regime run ID for regime-conditioned IC summary (requires CRYPTO_ANALYZER_ENABLE_REGIMES=1)",
    )
    ap.add_argument(
        "--execution-evidence",
        dest="execution_evidence",
        action="store_true",
        help="Write capacity curve CSV and execution_evidence.json per signal for promotion gates",
    )
    ap.add_argument(
        "--reality-check",
        dest="reality_check",
        action="store_true",
        help="Run Reality Check (RC) over signal×horizon family; write RC artifacts and registry metrics",
    )
    ap.add_argument("--rc-metric", dest="rc_metric", choices=["mean_ic", "deflated_sharpe"], default="mean_ic")
    ap.add_argument(
        "--rc-horizon",
        dest="rc_horizon",
        type=int,
        default=1,
        help="Horizon for mean_ic (required when rc-metric=mean_ic)",
    )
    ap.add_argument("--rc-n-sim", dest="rc_n_sim", type=int, default=200)
    ap.add_argument("--rc-seed", dest="rc_seed", type=int, default=42)
    ap.add_argument(
        "--no-cache",
        dest="no_rc_cache",
        action="store_true",
        help="Disable RC null cache (env CRYPTO_ANALYZER_NO_CACHE=1 also disables)",
    )
    ap.add_argument("--rc-method", dest="rc_method", choices=["stationary", "block_fixed"], default="stationary")
    ap.add_argument("--rc-avg-block-length", dest="rc_avg_block_length", type=int, default=12)
    args = ap.parse_args()

    # Fail fast if --regimes set but regimes disabled (no silent ignore)
    regime_opt = (getattr(args, "regimes", None) or "").strip()
    if regime_opt:
        try:
            from crypto_analyzer.regimes import is_regimes_enabled
        except Exception:

            def is_regimes_enabled() -> bool:
                return False

        if not is_regimes_enabled():
            print(
                "Error: --regimes is set but regimes are disabled. "
                "Set CRYPTO_ANALYZER_ENABLE_REGIMES=1 to enable regime-conditioned output.",
                file=sys.stderr,
            )
            return 1

    db = args.db or (db_path() if callable(db_path) else db_path())
    out_dir = Path(args.out_dir)
    ensure_dir(out_dir)
    for sub in ("csv", "charts", "manifests", "health"):
        ensure_dir(out_dir / sub)

    profile_enabled = os.environ.get("CRYPTO_ANALYZER_PROFILE", "").strip() == "1"
    profile_start = time.perf_counter() if profile_enabled else None

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
        "| cost model | fee + slippage (bps) |",
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

    # Regime state (exact join, no ffill): load once when --regimes set for per-signal artifacts
    regime_labels_series = None
    regime_run_id_early = (getattr(args, "regimes", None) or "").strip()
    try:
        from crypto_analyzer.regimes import is_regimes_enabled
    except Exception:

        def is_regimes_enabled() -> bool:
            return False

    if is_regimes_enabled() and regime_run_id_early:
        regime_rows = []
        try:
            conn = sqlite3.connect(db)
            cur = conn.execute(
                "SELECT ts_utc, regime_label FROM regime_states WHERE regime_run_id = ? ORDER BY ts_utc",
                (regime_run_id_early,),
            )
            regime_rows = cur.fetchall()
            conn.close()
        except sqlite3.OperationalError:
            pass
        if regime_rows:
            regime_df = pd.DataFrame(regime_rows, columns=["ts_utc", "regime_label"])
            regime_df["ts_utc"] = pd.to_datetime(regime_df["ts_utc"])
            # Exact join: reindex to returns index, no ffill/bfill (missing -> unknown)
            reg_ser = regime_df.set_index("ts_utc")["regime_label"]
            regime_labels_series = reg_ser.reindex(returns_df.index).fillna("unknown").astype(str)

    # Compute run_id and dataset_id once for ValidationBundles and deterministic paths
    import hashlib as _hl
    import json as _js

    config_blob_early = _js.dumps(
        {"freq": args.freq, "signals": args.signals, "portfolio": args.portfolio, "cov_method": args.cov_method},
        sort_keys=True,
    )
    config_hash_early = _hl.sha256(config_blob_early.encode()).hexdigest()[:16]
    ts_now_early = now_utc_iso()
    run_id_early = stable_run_id(
        {"name": "research_report_v2", "ts_utc": ts_now_early, "config_hash": config_hash_early}
    )
    _fp_early = compute_dataset_fingerprint(str(db))
    _computed_dataset_id_early = dataset_id_from_fingerprint(_fp_early)
    deterministic_time_used = bool(os.environ.get("CRYPTO_ANALYZER_DETERMINISTIC_TIME", "").strip())

    portfolio_pnls = {}
    walk_forward_rows = []
    bundle_output_paths: list[str] = []
    _regime_coverage_rel_path: str | None = None  # written once per run when --regimes set
    rc_ic_series_by_hypothesis: dict = {}  # signal|horizon -> IC Series for Reality Check when --reality-check
    _rc_family_id: str | None = None
    _rc_result: dict | None = None
    _rc_observed_stats: pd.Series | None = None  # for sweep registry persistence
    _rc_family_payload: dict | None = None  # canonical family payload for sweep_families.sweep_payload_json

    for name, sig_df in (orth_dict or signals_dict).items():
        if sig_df is None or sig_df.empty:
            continue
        ranks = rank_signal_df(sig_df)
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
                        b = (
                            exp["beta_btc_72"].loc[last_t]
                            if last_t in exp["beta_btc_72"].index
                            else exp["beta_btc_72"].iloc[-1]
                        )
                        constraints["betas"] = b
                w, diag = optimize_long_short_portfolio(er, cov, constraints)
                if not w.empty:
                    lines.append(f"### {name} (advanced diagnostics)")
                    lines.append(
                        f"Beta: {diag.get('achieved_beta', np.nan):.4f}  Gross: {diag.get('gross_leverage', 0):.4f}  Net: {diag.get('net_exposure', 0):.4f}  N_assets: {diag.get('n_assets', 0)}"
                    )
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
            walk_forward_rows.append(
                {
                    "strategy": name,
                    "train_sharpe": np.nan,
                    "test_sharpe": float(port_ret_net.mean() / port_ret_net.std())
                    if port_ret_net.std() and port_ret_net.std() > 0
                    else np.nan,
                }
            )

        # ValidationBundle per signal: IC by horizon, decay table, artifact paths (relative to out_dir for determinism)
        try:
            csv_dir = out_dir / "csv"
            ensure_dir(csv_dir)
            horizons = VALIDATION_HORIZONS
            ic_summary_by_horizon: dict = {}
            ic_series_path_by_horizon: dict = {}
            ic_series_by_horizon: dict = {}
            for h in horizons:
                fwd = compute_forward_returns(returns_df, h)
                ic_ts = information_coefficient(sig_df, fwd, method="spearman")
                ic_series_by_horizon[h] = ic_ts
                if getattr(args, "reality_check", False):
                    rc_ic_series_by_hypothesis[f"{name}|{h}"] = ic_ts
                ic_summary_by_horizon[h] = ic_summary(ic_ts)
                path_ic = csv_dir / f"ic_series_{name}_h{h}_{run_id_early}.csv"
                write_df_csv_stable(ic_ts.to_frame(name="ic"), path_ic)
                ic_series_path_by_horizon[h] = str(path_ic.relative_to(out_dir))
                bundle_output_paths.append(str(path_ic))
            decay_df = ic_decay(sig_df, returns_df, horizons, method="spearman")
            ic_decay_table = decay_df.to_dict(orient="records") if not decay_df.empty else []
            path_decay = csv_dir / f"ic_decay_{name}_{run_id_early}.csv"
            if not decay_df.empty:
                write_df_csv_stable(decay_df, path_decay)
                bundle_output_paths.append(str(path_decay))
            path_turnover = csv_dir / f"turnover_{name}_{run_id_early}.csv"
            write_df_csv_stable(turnover_ser.to_frame(name="turnover"), path_turnover)
            bundle_output_paths.append(str(path_turnover))
            meta = {
                "config_hash": config_hash_early,
                "git_commit": get_git_commit(),
                "engine_version": None,
                "as_of_lag_bars": 1,
                "deterministic_time_used": deterministic_time_used,
            }
            ic_summary_by_regime_path_rel: str | None = None
            ic_decay_by_regime_path_rel: str | None = None
            regime_coverage_path_rel: str | None = None
            if regime_labels_series is not None and not regime_labels_series.empty:
                if _regime_coverage_rel_path is None:
                    coverage_dict = regime_coverage(regime_labels_series)
                    path_coverage = csv_dir / f"regime_coverage_{run_id_early}.json"
                    write_json_sorted(coverage_dict, path_coverage)
                    _regime_coverage_rel_path = str(path_coverage.relative_to(out_dir))
                    bundle_output_paths.append(str(path_coverage))
                regime_coverage_path_rel = _regime_coverage_rel_path
                ic_summary_reg = ic_summary_by_regime_multi(ic_series_by_horizon, regime_labels_series)
                ic_decay_reg = ic_decay_by_regime(ic_series_by_horizon, regime_labels_series)
                path_ic_summary_reg = csv_dir / f"ic_summary_by_regime_{name}_{run_id_early}.csv"
                path_ic_decay_reg = csv_dir / f"ic_decay_by_regime_{name}_{run_id_early}.csv"
                write_df_csv_stable(ic_summary_reg, path_ic_summary_reg)
                write_df_csv_stable(ic_decay_reg, path_ic_decay_reg)
                bundle_output_paths.append(str(path_ic_summary_reg))
                bundle_output_paths.append(str(path_ic_decay_reg))
                ic_summary_by_regime_path_rel = str(path_ic_summary_reg.relative_to(out_dir))
                ic_decay_by_regime_path_rel = str(path_ic_decay_reg.relative_to(out_dir))
                meta["regime_run_id"] = regime_run_id_early
                meta["regime_join_policy"] = "exact"
                meta["decision_lag_bars"] = 1
                meta["regime_coverage_summary"] = regime_coverage(regime_labels_series)
            bundle = ValidationBundle(
                run_id=run_id_early,
                dataset_id=getattr(args, "dataset_id", None) or _computed_dataset_id_early,
                signal_name=name,
                freq=args.freq,
                horizons=horizons,
                ic_summary_by_horizon=ic_summary_by_horizon,
                ic_decay_table=ic_decay_table,
                meta=meta,
                ic_series_path_by_horizon=ic_series_path_by_horizon,
                ic_decay_path=str(path_decay.relative_to(out_dir)) if not decay_df.empty else None,
                turnover_path=str(path_turnover.relative_to(out_dir)),
                gross_returns_path=None,
                net_returns_path=None,
                ic_summary_by_regime_path=ic_summary_by_regime_path_rel,
                ic_decay_by_regime_path=ic_decay_by_regime_path_rel,
                regime_coverage_path=regime_coverage_path_rel,
            )
            bundle_path = csv_dir / f"validation_bundle_{name}_{run_id_early}.json"
            write_json_sorted(bundle.to_dict(), bundle_path)
            bundle_output_paths.append(str(bundle_path))

            # Execution evidence artifacts (optional; do not extend ValidationBundle)
            if getattr(args, "execution_evidence", False):
                try:
                    from crypto_analyzer.execution_cost import capacity_curve
                    from crypto_analyzer.promotion.execution_evidence import (
                        ExecutionEvidence,
                        execution_evidence_to_json,
                    )

                    cap_df = capacity_curve(
                        port_ret,
                        turnover_ser,
                        freq=args.freq,
                        fee_bps=args.fee_bps,
                        slippage_bps=args.slippage_bps,
                    )
                    path_cap = csv_dir / f"capacity_curve_{name}_{run_id_early}.csv"
                    write_df_csv_stable(cap_df, path_cap)
                    cap_path_rel = str(path_cap.relative_to(out_dir))
                    cost_config = {
                        "fee_bps": args.fee_bps,
                        "slippage_bps": args.slippage_bps,
                        "spread_vol_scale": 0.0,
                        "use_participation_impact": False,
                        "impact_bps_per_participation": 5.0,
                        "max_participation_pct": 10.0,
                    }
                    max_participation_rate = cost_config["max_participation_pct"]
                    exec_ev = ExecutionEvidence(
                        min_liquidity_usd=None,
                        max_participation_rate=max_participation_rate,
                        spread_model=None,
                        impact_model=None,
                        capacity_curve_path=cap_path_rel,
                        cost_config=cost_config,
                        notes=None,
                    )
                    path_exec_ev = csv_dir / f"execution_evidence_{name}_{run_id_early}.json"
                    with open(path_exec_ev, "w", encoding="utf-8") as f:
                        f.write(execution_evidence_to_json(exec_ev))
                except Exception as exec_e:
                    print(f"Execution evidence skip ({name}):", exec_e)
        except Exception as e:
            print(f"ValidationBundle skip ({name}):", e)

    # ---- Reality Check (opt-in) ----
    if getattr(args, "reality_check", False) and rc_ic_series_by_hypothesis:
        try:
            from crypto_analyzer.stats.rc_cache import (
                get_rc_cache_key,
                is_cache_disabled,
                load_cached_null_max,
                save_cached_null_max,
            )
            from crypto_analyzer.stats.reality_check import (
                RealityCheckConfig,
                make_null_generator_stationary,
                run_reality_check,
            )
            from crypto_analyzer.sweeps.family_id import compute_family_id

            signal_names_sorted = sorted((orth_dict or signals_dict).keys())
            horizons_sorted = sorted(VALIDATION_HORIZONS)
            family_payload = {
                "config_hash": config_hash_early,
                "signals": signal_names_sorted,
                "horizons": horizons_sorted,
                "regime_run_id": regime_run_id_early or "",
            }
            _rc_family_id = compute_family_id(family_payload)
            _rc_family_payload = family_payload
            observed_stats = pd.Series(
                {hid: float(s.mean()) for hid, s in rc_ic_series_by_hypothesis.items()}
            ).sort_index()
            _rc_observed_stats = observed_stats
            cfg = RealityCheckConfig(
                metric=getattr(args, "rc_metric", "mean_ic"),
                horizon=getattr(args, "rc_horizon", 1),
                n_sim=getattr(args, "rc_n_sim", 200),
                seed=getattr(args, "rc_seed", 42),
                method=getattr(args, "rc_method", "stationary"),
                avg_block_length=getattr(args, "rc_avg_block_length", 12),
                block_size=getattr(args, "rc_avg_block_length", 12),
            )
            cache_dir = out_dir / "rc_cache"
            use_cache = not is_cache_disabled(no_cache_flag=getattr(args, "no_rc_cache", False))
            cached_null_max = None
            if use_cache:
                _ds_id = getattr(args, "dataset_id", None) or _computed_dataset_id_early
                _key = get_rc_cache_key(
                    _rc_family_id,
                    _ds_id or "",
                    get_git_commit(),
                    cfg.metric,
                    cfg.horizon,
                    cfg.n_sim,
                    cfg.seed,
                    cfg.method,
                    cfg.avg_block_length,
                )
                cached_null_max = load_cached_null_max(cache_dir, _key)
            null_gen = make_null_generator_stationary(rc_ic_series_by_hypothesis, cfg)
            _rc_result = run_reality_check(observed_stats, null_gen, cfg, cached_null_max=cached_null_max)
            if (
                use_cache
                and cached_null_max is None
                and _rc_result.get("null_max_distribution") is not None
                and len(_rc_result["null_max_distribution"]) > 0
            ):
                _ds_id = getattr(args, "dataset_id", None) or _computed_dataset_id_early
                _key = get_rc_cache_key(
                    _rc_family_id,
                    _ds_id or "",
                    get_git_commit(),
                    cfg.metric,
                    cfg.horizon,
                    cfg.n_sim,
                    cfg.seed,
                    cfg.method,
                    cfg.avg_block_length,
                )
                save_cached_null_max(cache_dir, _key, _rc_result["null_max_distribution"])
            _rc_result["family_id"] = _rc_family_id
            csv_dir = out_dir / "csv"
            ensure_dir(csv_dir)
            summary_path = csv_dir / f"reality_check_summary_{_rc_family_id}.json"
            summary_json = {
                k: v for k, v in _rc_result.items() if k not in ("null_max_distribution", "rw_adjusted_p_values")
            }
            summary_json["observed_stats"] = {k: float(v) for k, v in observed_stats.items()}
            if "null_max_distribution" in _rc_result:
                nd = _rc_result["null_max_distribution"]
                summary_json["null_max_sample"] = float(nd[0]) if len(nd) else None
            write_json_sorted(summary_json, summary_path)
            bundle_output_paths.append(str(summary_path))
            null_max_path = csv_dir / f"reality_check_null_max_{_rc_family_id}.csv"
            if _rc_result.get("null_max_distribution") is not None and len(_rc_result["null_max_distribution"]) > 0:
                write_df_csv_stable(pd.DataFrame({"null_max": _rc_result["null_max_distribution"]}), null_max_path)
                bundle_output_paths.append(str(null_max_path))
        except Exception as e:
            print("Reality Check skip:", e)
            _rc_family_id = None
            _rc_result = None

    # ---- Deflated Sharpe ----
    lines.append("## 4) Overfitting defenses")
    lines.append(f"Deflated Sharpe (n_trials={args.n_trials}):")
    for name, pnl in portfolio_pnls.items():
        if len(pnl) < 10:
            continue
        dsr = deflated_sharpe_ratio(pnl, args.freq, args.n_trials, skew_kurtosis_optional=True)
        lines.append(
            f"- **{name}**: raw_sr={dsr.get('raw_sr', np.nan):.4f}  deflated_sr={dsr.get('deflated_sr', np.nan):.4f}"
        )
    wf_df = pd.DataFrame(walk_forward_rows) if walk_forward_rows else pd.DataFrame()
    pbo = pbo_proxy_walkforward(wf_df)
    lines.append(f"PBO proxy: {pbo.get('pbo_proxy', np.nan)}  ({pbo.get('explanation', '')})")
    lines.append(reality_check_warning(len(signals_dict), len(portfolio_pnls)))
    lines.append("")

    # ---- Regime-conditioned ----
    lines.append("## 5) Regime-conditioned performance")
    disp_series = compute_dispersion_series(returns_df) if not returns_df.empty else pd.Series(dtype=float)
    disp_z = (
        dispersion_zscore_series(disp_series, DISPERSION_WINDOW)
        if len(disp_series) >= DISPERSION_WINDOW
        else pd.Series(dtype=float)
    )
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

    # Regime-conditioned summary (only when --regimes set and regime artifacts were written)
    if regime_run_id_early and _regime_coverage_rel_path is not None:
        lines.append("## Regime-conditioned summary")
        lines.append(
            f"Regime run: `{regime_run_id_early}`. Join: exact. Artifacts: `csv/ic_summary_by_regime_*`, `csv/ic_decay_by_regime_*`, `csv/regime_coverage_*.json`."
        )
        lines.append("")

    report_path = out_dir / timestamped_filename("research_v2", "md", sep="_")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Report: {report_path}")

    output_paths = [str(report_path)] + bundle_output_paths

    # Research Health Summary + health_summary.json
    health_dir = out_dir / "health"
    try:
        data_coverage = {"n_assets": n_assets, "n_bars": len(returns_df)}
        signal_stability = {}
        if len(signals_dict) >= 1 and not returns_df.empty:
            sig_first = next(iter(signals_dict.values()))
            if sig_first is not None and not sig_first.empty:
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
            betas_dict, r2_mf, resid_mf = rolling_multifactor_ols(returns_df, factor_matrix, window=72, min_obs=24)
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
            config_dict={
                "freq": args.freq,
                "signals": args.signals,
                "portfolio": args.portfolio,
                "cov_method": args.cov_method,
            },
            metrics_dict={
                k: float(v.mean() / v.std()) if v.std() and v.std() > 0 else np.nan for k, v in portfolio_pnls.items()
            },
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
            metrics_summary = {
                k: float(v.mean() / v.std()) if v.std() and v.std() > 0 else np.nan for k, v in portfolio_pnls.items()
            }
            outputs_for_manifest = list(output_paths)
            if profile_enabled and profile_start is not None:
                total_sec = time.perf_counter() - profile_start
                timings_path = out_dir / "timings.json"
                write_json_sorted(
                    {"stages": [{"name": "total", "seconds": round(total_sec, 6)}], "run_id": run_id_early},
                    timings_path,
                )
                outputs_for_manifest.append(str(timings_path))
            outputs_with_hashes = snapshot_outputs(outputs_for_manifest)
            manifest = make_run_manifest(
                name=getattr(args, "run_name", None) or "research_report_v2",
                args={
                    "freq": args.freq,
                    "signals": args.signals,
                    "portfolio": args.portfolio,
                    "cov_method": args.cov_method,
                },
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

        pnl_sharpes = {
            k: float(v.mean() / v.std()) if v.std() and v.std() > 0 else float("nan") for k, v in portfolio_pnls.items()
        }
        canonical_metrics: dict = {
            "universe_size": float(n_assets),
        }
        if pnl_sharpes:
            _sharpe_agg = safe_nanmean(list(pnl_sharpes.values()))
            if _sharpe_agg is not None:
                canonical_metrics["sharpe"] = _sharpe_agg
        for k, v in pnl_sharpes.items():
            canonical_metrics[f"sharpe_{k}"] = v

        if portfolio_pnls:
            for k, pnl in portfolio_pnls.items():
                eq = (1 + pnl).cumprod()
                dd = (eq.cummax() - eq) / eq.cummax()
                canonical_metrics[f"max_drawdown_{k}"] = float(dd.max()) if not dd.empty else float("nan")
            canonical_metrics["max_drawdown"] = float(
                np.nanmax([canonical_metrics.get(f"max_drawdown_{k}", float("nan")) for k in portfolio_pnls])
            )

        if signals_dict:
            fwd1 = compute_forward_returns(returns_df, 1)
            p_values_series = pd.Series(dtype=float)
            for sname, sig in signals_dict.items():
                ic_ts = information_coefficient(sig, fwd1, method="spearman")
                if not ic_ts.empty and ic_ts.notna().any():
                    canonical_metrics[f"mean_ic_{sname}"] = float(ic_ts.mean())
                    s = ic_summary(ic_ts)
                    t_stat = s.get("t_stat")
                    if t_stat is not None and np.isfinite(t_stat):
                        # Two-tailed p from t (normal approximation)
                        z = abs(float(t_stat))
                        p_val = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2.0))))
                        p_val = min(1.0, max(1e-16, p_val))
                        p_values_series[sname] = p_val
                        canonical_metrics[f"p_value_raw_{sname}"] = p_val
            if len(p_values_series) >= 2:
                adj, discoveries = adjust_pvalues(p_values_series, method="bh", q=0.05)
                for sname in p_values_series.index:
                    if sname in adj.index and np.isfinite(adj[sname]):
                        canonical_metrics[f"p_value_adj_bh_{sname}"] = float(adj[sname])
                canonical_metrics["p_value_family_adjusted"] = 1.0
            elif len(p_values_series) == 1:
                canonical_metrics["p_value_family_adjusted"] = 0.0
            ic_vals = [canonical_metrics[k] for k in canonical_metrics if k.startswith("mean_ic_")]
            if ic_vals:
                canonical_metrics["mean_ic"] = float(np.nanmean(ic_vals))

        if portfolio_pnls:
            turnover_vals = []
            for k in portfolio_pnls:
                sig = signals_dict.get(k)
                if sig is None and orth_dict:
                    sig = orth_dict.get(k)
                if sig is not None and not sig.empty:
                    r = rank_signal_df(sig)
                    w = long_short_from_ranks(r, args.top_k, args.bottom_k, gross_leverage=1.0)
                    t = turnover_from_weights(w)
                    turnover_vals.append(float(t.mean()))
            if turnover_vals:
                canonical_metrics["turnover"] = float(np.nanmean(turnover_vals))

        canonical_metrics.update(mf_metrics)
        if _rc_result is not None and _rc_family_id is not None:
            canonical_metrics["family_id"] = _rc_family_id
            canonical_metrics["rc_p_value"] = _rc_result["rc_p_value"]
            canonical_metrics["rc_observed_max"] = _rc_result["observed_max"]
            canonical_metrics["rc_metric"] = _rc_result.get("rc_metric", "mean_ic")
            canonical_metrics["rc_horizon"] = (
                float(_rc_result["rc_horizon"]) if _rc_result.get("rc_horizon") is not None else None
            )
            canonical_metrics["rc_n_sim"] = _rc_result.get("n_sim", 0)
            canonical_metrics["rc_seed"] = _rc_result.get("rc_seed")
            canonical_metrics["rc_method"] = _rc_result.get("rc_method", "stationary")
            canonical_metrics["rc_avg_block_length"] = _rc_result.get("rc_avg_block_length")

        env_fp = str(get_env_fingerprint())
        experiment_db_path = os.environ.get("EXPERIMENT_DB_PATH", str(out_dir / "experiments.db"))
        from crypto_analyzer.experiments import parse_tags

        tags_list = parse_tags(args.tags) if getattr(args, "tags", None) else []
        params_dict = {
            "freq": args.freq,
            "signals": args.signals,
            "portfolio": args.portfolio,
            "cov_method": args.cov_method,
        }
        if "sharpe" not in canonical_metrics:
            params_dict["sharpe_unavailable_reason"] = "insufficient_assets_or_no_valid_pnl"
        params_dict["dataset_fingerprint"] = fingerprint_to_json(_fp_early)
        experiment_row = {
            "run_id": run_id_early,
            "ts_utc": ts_now_early,
            "git_commit": get_git_commit(),
            "spec_version": RESEARCH_SPEC_VERSION,
            "out_dir": str(out_dir),
            "notes": getattr(args, "notes", "") or "",
            "data_start": str(returns_df.index.min()) if not returns_df.empty else "",
            "data_end": str(returns_df.index.max()) if not returns_df.empty else "",
            "config_hash": config_hash_early,
            "env_fingerprint": env_fp,
            "hypothesis": getattr(args, "hypothesis", None) or "",
            "tags_json": tags_list,
            "dataset_id": getattr(args, "dataset_id", None) or _computed_dataset_id_early,
            "params_json": params_dict,
        }

        artifacts_for_db = [{"artifact_path": p, "sha256": compute_file_sha256(p)} for p in output_paths]

        record_experiment_run(
            db_path=experiment_db_path,
            experiment_row=experiment_row,
            metrics_dict=canonical_metrics,
            artifacts_list=artifacts_for_db,
        )
        print(f"Experiment recorded: {run_id_early} -> {experiment_db_path}")

        # Sweep registry (opt-in): persist family + hypotheses when --reality-check and Phase 3 tables exist
        if (
            getattr(args, "reality_check", False)
            and _rc_family_id is not None
            and _rc_result is not None
            and _rc_observed_stats is not None
            and _rc_family_payload is not None
        ):
            try:
                from crypto_analyzer.sweeps.hypothesis_id import compute_hypothesis_id
                from crypto_analyzer.sweeps.store_sqlite import persist_sweep_family

                sweep_payload_json = json.dumps(_rc_family_payload, sort_keys=True)
                hypotheses = []
                for key in _rc_observed_stats.index:
                    parts = str(key).split("|", 1)
                    signal_name = parts[0] if parts else ""
                    horizon = 0
                    if len(parts) >= 2:
                        try:
                            horizon = int(parts[1])
                        except (ValueError, TypeError):
                            horizon = 0
                    payload = {
                        "signal_name": signal_name,
                        "horizon": horizon,
                        "estimator": None,
                        "params": None,
                        "regime_run_id": regime_run_id_early or "",
                    }
                    hypothesis_id = compute_hypothesis_id(payload)
                    hypotheses.append(
                        {
                            "hypothesis_id": hypothesis_id,
                            "signal_name": signal_name,
                            "horizon": horizon,
                            "estimator": None,
                            "params_json": None,
                            "regime_run_id": regime_run_id_early or None,
                        }
                    )
                conn = sqlite3.connect(experiment_db_path)
                try:
                    if persist_sweep_family(
                        conn,
                        family_id=_rc_family_id,
                        dataset_id=experiment_row["dataset_id"],
                        sweep_payload_json=sweep_payload_json,
                        run_id=run_id_early,
                        sweep_name=None,
                        git_commit=get_git_commit(),
                        config_hash=config_hash_early,
                        hypotheses=hypotheses,
                    ):
                        print(f"Sweep registry: persisted family {_rc_family_id} with {len(hypotheses)} hypotheses")
                finally:
                    conn.close()
            except Exception as sweep_err:
                print("Sweep registry skip:", sweep_err)
    except Exception as e:
        print("SQLite experiment registry skip:", e)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
