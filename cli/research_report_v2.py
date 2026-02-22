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
from crypto_analyzer.data import get_factor_returns, load_bars, load_factor_run
from crypto_analyzer.dataset import compute_dataset_fingerprint, dataset_id_from_fingerprint, fingerprint_to_json
from crypto_analyzer.dataset_v2 import get_dataset_id_v2
from crypto_analyzer.diagnostics import build_health_summary, rolling_ic_stability
from crypto_analyzer.evaluation import conditional_metrics, lead_lag_analysis
from crypto_analyzer.experiments import log_experiment, record_experiment_run
from crypto_analyzer.factors import build_factor_matrix, rolling_multifactor_ols
from crypto_analyzer.governance import (
    compute_run_key,
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
from crypto_analyzer.multiple_testing import (
    deflated_sharpe_ratio,
    pbo_cscv,
    pbo_proxy_walkforward,
    reality_check_warning,
)
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
    liquidity_shock_reversion_variants,
    orthogonalize_signals,
    value_vs_beta,
)
from crypto_analyzer.statistics import hac_mean_inference, safe_nanmean
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
    ap.add_argument(
        "--n-trials",
        default="auto",
        help="Deflated Sharpe: 'auto' (default) = compute Neff from strategy returns; or integer (e.g. 50). Do not infer intent from value.",
    )
    ap.add_argument(
        "--hac-lags",
        default="auto",
        dest="hac_lags",
        help="HAC (Newey-West) lag: 'auto' (default) or integer. Used for mean-return inference.",
    )
    ap.add_argument("--pbo-cscv-blocks", type=int, default=16, dest="pbo_cscv_blocks", help="CSCV number of blocks S (default 16).")
    ap.add_argument(
        "--pbo-cscv-max-splits",
        type=int,
        default=20000,
        dest="pbo_cscv_max_splits",
        help="CSCV cap on enumerated splits; beyond this, random-sample with seed.",
    )
    ap.add_argument(
        "--pbo-metric",
        choices=["mean", "sharpe"],
        default="mean",
        dest="pbo_metric",
        help="CSCV in-fold metric: mean or sharpe.",
    )
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
        "--factor-run-id",
        dest="factor_run_id",
        default=None,
        metavar="FACTOR_RUN_ID",
        help="Use materialized factor run from DB (factor_betas, residual_returns); default: compute in-memory",
    )
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
    ap.add_argument(
        "--case-study",
        dest="case_study",
        choices=["liqshock"],
        default=None,
        help="Use case-study memo renderer (e.g. liqshock). Default report unchanged when not set.",
    )
    ap.add_argument(
        "--min-bars",
        dest="min_bars",
        type=int,
        default=None,
        help="Minimum bars per pair (quality gate). Default: use config. Does not create more assets.",
    )
    ap.add_argument(
        "--dex-only",
        dest="dex_only",
        action="store_true",
        help="Exclude spot from research universe so returns columns align with bars (for hiring run).",
    )
    ap.add_argument(
        "--top10-p10-liq-floor",
        dest="top10_p10_liq_floor",
        type=int,
        default=250000,
        help="Top 10 eligibility: p10(liquidity_usd) >= this (USD). Default 250000.",
    )
    args = ap.parse_args()

    # Normalize --n-trials: "auto" (default) vs explicit int; do not infer intent from value
    _n_trials_raw = getattr(args, "n_trials", "auto")
    if str(_n_trials_raw).strip().lower() == "auto":
        args._n_trials_mode = "auto"
        args._n_trials_int = None
    else:
        try:
            args._n_trials_int = int(float(str(_n_trials_raw)))
            args._n_trials_mode = "user"
        except (ValueError, TypeError):
            args._n_trials_mode = "auto"
            args._n_trials_int = None

    # Normalize --hac-lags: "auto" vs explicit int
    _hac_raw = getattr(args, "hac_lags", "auto")
    if str(_hac_raw).strip().lower() == "auto":
        args._hac_lags_int = None
    else:
        try:
            args._hac_lags_int = int(float(str(_hac_raw)))
            args._hac_lags_int = max(0, args._hac_lags_int)
        except (ValueError, TypeError):
            args._hac_lags_int = None

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
    # Optional: load materialized factor run when --factor-run-id set
    factor_run_loaded = None
    if getattr(args, "factor_run_id", None):
        fid = (args.factor_run_id or "").strip()
        if fid:
            factor_run_loaded = load_factor_run(db, fid)
            if factor_run_loaded is None:
                print(
                    f"Error: --factor-run-id '{fid}' not found or empty in DB. "
                    "Run factor materialize first or omit --factor-run-id for in-memory factors.",
                    file=sys.stderr,
                )
                return 1
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

    include_spot = not getattr(args, "dex_only", False)
    returns_df, meta_df = get_research_assets(
        db,
        args.freq,
        include_spot=include_spot,
        min_bars_override=getattr(args, "min_bars", None),
    )
    n_assets = returns_df.shape[1] if not returns_df.empty else 0
    meta_dict = meta_df.set_index("asset_id")["label"].to_dict() if not meta_df.empty else {}
    bars_match_n_ret: int = 0
    bars_match_n_match: int = 0
    bars_match_pct: float = 0.0
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
        f"| deflated_sharpe n_trials | {args.n_trials if hasattr(args, 'n_trials') else 'auto'} |",
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

    signal_names = [s.strip() for s in args.signals.split(",") if s.strip()]

    # Bars + liquidity panel (only when liquidity_shock_reversion requested)
    liquidity_panel = None
    roll_vol_panel = None
    if "liquidity_shock_reversion" in signal_names and not returns_df.empty:
        bars = load_bars(args.freq, db_path_override=db, min_bars=None)
        if not bars.empty:
            bars = bars.copy()
            bars["pair_id"] = bars["chain_id"].astype(str) + ":" + bars["pair_address"].astype(str)
            bars_unique_pairs = int(bars["pair_id"].nunique())
            bars_start = bars["ts_utc"].min()
            bars_end = bars["ts_utc"].max()
            bars = bars[bars["pair_id"].isin(returns_df.columns)]
            if not bars.empty:
                liquidity_panel = bars.pivot_table(index="ts_utc", columns="pair_id", values="liquidity_usd")
                roll_vol_panel = bars.pivot_table(index="ts_utc", columns="pair_id", values="roll_vol")
                liquidity_panel = liquidity_panel.reindex(index=returns_df.index, columns=returns_df.columns)
                roll_vol_panel = roll_vol_panel.reindex(index=returns_df.index, columns=returns_df.columns)
                n_ret = len(returns_df.columns)
                n_match = len(liquidity_panel.columns.intersection(returns_df.columns))
                pct = 100.0 * n_match / n_ret if n_ret else 0.0
                bars_match_n_ret, bars_match_n_match, bars_match_pct = n_ret, n_match, pct
                _diag = "liquidity_shock_reversion" in signal_names or getattr(args, "case_study", None) == "liqshock"
                if _diag:
                    ret_start = returns_df.index.min()
                    ret_end = returns_df.index.max()
                    print(f"returns columns: {n_ret}")
                    print(f"returns date range: [{ret_start}, {ret_end}]")
                    print(f"bars unique pair_ids: {bars_unique_pairs}")
                    print(f"bars date range: [{bars_start}, {bars_end}]")
                    print(f"bars columns matched: {n_match} ({pct:.1f}%)")

    # Build signals (including institutional composites)
    sig_mom = signal_momentum_24h(returns_df, args.freq) if n_assets >= 1 else pd.DataFrame()
    sig_clean = clean_momentum(returns_df, args.freq, factor_ret) if not returns_df.empty else pd.DataFrame()
    sig_value = value_vs_beta(returns_df, args.freq, factor_ret) if not returns_df.empty else None
    if sig_value is not None and sig_value.empty:
        sig_value = None

    signals_dict = {}
    if "clean_momentum" in signal_names and not sig_clean.empty:
        signals_dict["clean_momentum"] = sig_clean
    if "value_vs_beta" in signal_names and sig_value is not None and not sig_value.empty:
        signals_dict["value_vs_beta"] = sig_value
    if "momentum_24h" in signal_names and not sig_mom.empty:
        signals_dict["momentum_24h"] = sig_mom
    if "liquidity_shock_reversion" in signal_names and liquidity_panel is not None:
        liqshock_variants = liquidity_shock_reversion_variants(
            liquidity_panel=liquidity_panel,
            target_index=returns_df.index,
            target_columns=returns_df.columns,
            roll_vol_panel=roll_vol_panel,
        )
        signals_dict.update(liqshock_variants)

    # ---- Orthogonalized signals section ----
    lines.append("## 2) Orthogonalized signals")
    if signal_names == ["liquidity_shock_reversion"]:
        orth_dict = dict(signals_dict)
        lines.append("*Liqshock-only run: orthogonalization skipped (16 variants).*")
    elif len(signals_dict) >= 2:
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
            with sqlite3.connect(db) as conn:
                cur = conn.execute(
                    "SELECT ts_utc, regime_label FROM regime_states WHERE regime_run_id = ? ORDER BY ts_utc",
                    (regime_run_id_early,),
                )
                regime_rows = cur.fetchall()
        except sqlite3.OperationalError:
            pass
        if regime_rows:
            regime_df = pd.DataFrame(regime_rows, columns=["ts_utc", "regime_label"])
            regime_df["ts_utc"] = pd.to_datetime(regime_df["ts_utc"])
            # Exact join: reindex to returns index, no ffill/bfill (missing -> unknown)
            reg_ser = regime_df.set_index("ts_utc")["regime_label"]
            regime_labels_series = reg_ser.reindex(returns_df.index).fillna("unknown").astype(str)

    # Compute run_id (instance id), run_key (semantic), dataset_id v1/v2 once for ValidationBundles and manifests
    import hashlib as _hl
    import json as _js

    config_blob_early = _js.dumps(
        {"freq": args.freq, "signals": args.signals, "portfolio": args.portfolio, "cov_method": args.cov_method},
        sort_keys=True,
    )
    config_hash_early = _hl.sha256(config_blob_early.encode()).hexdigest()[:16]
    ts_now_early = now_utc_iso()
    # run_id_early = run_instance_id (for filenames and PK; may include timestamp for uniqueness)
    run_id_early = stable_run_id(
        {"name": "research_report_v2", "ts_utc": ts_now_early, "config_hash": config_hash_early}
    )
    _fp_early = compute_dataset_fingerprint(str(db))
    _computed_dataset_id_early = dataset_id_from_fingerprint(_fp_early)
    # Phase 1: dataset_id_v2 (logical content) and run_key (semantic, no timestamps)
    try:
        _dataset_id_v2_early, _dataset_hash_meta_early = get_dataset_id_v2(str(db), mode="STRICT")
    except Exception:
        _dataset_id_v2_early = ""
        _dataset_hash_meta_early = {}
    _engine_version_early = get_git_commit()
    from crypto_analyzer.spec import RESEARCH_SPEC_VERSION as _RESEARCH_SPEC_VERSION

    _semantic_payload_early = {
        "name": "research_report_v2",
        "dataset_id_v2": _dataset_id_v2_early,
        "config_hash": config_hash_early,
        "freq": args.freq,
        "signals": args.signals,
        "portfolio": args.portfolio,
        "cov_method": args.cov_method,
        "engine_version": _engine_version_early,
        "config_version": config_hash_early,
        "research_spec_version": _RESEARCH_SPEC_VERSION,
    }
    _run_key_early = compute_run_key(_semantic_payload_early) if _dataset_id_v2_early else ""
    deterministic_time_used = bool(os.environ.get("CRYPTO_ANALYZER_DETERMINISTIC_TIME", "").strip())

    portfolio_pnls = {}
    walk_forward_rows = []
    bundle_output_paths: list[str] = []
    non_monotone_capacity_curve_observed = False
    capacity_curve_written = False
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
                "engine_version": _engine_version_early,
                "as_of_lag_bars": 1,
                "deterministic_time_used": deterministic_time_used,
                "dataset_id_v2": _dataset_id_v2_early,
                "dataset_hash_algo": _dataset_hash_meta_early.get("dataset_hash_algo", "sqlite_logical_v2"),
                "dataset_hash_mode": _dataset_hash_meta_early.get("dataset_hash_mode", "STRICT"),
                "dataset_hash_scope": _dataset_hash_meta_early.get("dataset_hash_scope", []),
                "run_key": _run_key_early,
                "config_version": config_hash_early,
                "research_spec_version": _RESEARCH_SPEC_VERSION,
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
                    from crypto_analyzer.execution_cost import (
                        capacity_curve,
                        capacity_curve_is_non_monotone,
                    )
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
                        use_participation_impact=True,
                        impact_bps_per_participation=5.0,
                        max_participation_pct=10.0,
                    )
                    capacity_curve_written = True
                    if capacity_curve_is_non_monotone(cap_df):
                        non_monotone_capacity_curve_observed = True
                    path_cap = csv_dir / f"capacity_curve_{name}_{run_id_early}.csv"
                    write_df_csv_stable(cap_df, path_cap)
                    cap_path_rel = str(path_cap.relative_to(out_dir))
                    # cost_config must match what capacity_curve() used (participation-based impact)
                    cost_config = {
                        "fee_bps": args.fee_bps,
                        "slippage_bps": args.slippage_bps,
                        "spread_vol_scale": 0.0,
                        "use_participation_impact": True,
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

    # ---- Resolve n_trials for DSR (Neff when auto) ----
    n_trials_used: float = 50.0
    n_trials_user: int | None = None
    n_trials_eff_eigen: float | None = None
    n_trials_eff_inputs_total: int | None = None
    n_trials_eff_inputs_used: int | None = None
    if getattr(args, "_n_trials_mode", "auto") == "user" and getattr(args, "_n_trials_int", None) is not None:
        n_trials_used = float(args._n_trials_int)
        n_trials_user = args._n_trials_int
    else:
        # auto: compute Neff from strategy return correlation (trial universe = columns of R after alignment)
        from crypto_analyzer.multiple_testing import effective_trials_eigen

        if len(portfolio_pnls) >= 2:
            n_trials_eff_inputs_total = len(portfolio_pnls)
            try:
                common_idx = None
                for pnl in portfolio_pnls.values():
                    idx = pnl.dropna().index
                    common_idx = idx if common_idx is None else common_idx.intersection(idx)
                if common_idx is not None and len(common_idx) >= 10:
                    R = pd.DataFrame({k: v.reindex(common_idx) for k, v in portfolio_pnls.items()})
                    R = R.dropna(how="any")
                    if R.shape[1] >= 2 and R.shape[0] >= 10:
                        n_trials_eff_inputs_used = R.shape[1]
                        C = R.corr()
                        neff = effective_trials_eigen(C.values)
                        n_trials_eff_eigen = float(neff)
                        n_trials_used = max(1.0, round(neff))
            except Exception:
                pass
        if n_trials_eff_eigen is None:
            n_trials_used = max(1.0, n_trials_used)

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
            rw_adj = _rc_result.get("rw_adjusted_p_values")
            if rw_adj is not None and hasattr(rw_adj, "to_dict") and len(rw_adj) > 0:
                summary_json["rw_adjusted_p_values"] = {k: float(v) for k, v in rw_adj.items()}
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
    lines.append(
        f"Deflated Sharpe: n_trials_used={n_trials_used:.0f}  "
        f"n_trials_user={n_trials_user}  n_trials_eff_eigen={n_trials_eff_eigen}"
    )
    for name, pnl in portfolio_pnls.items():
        if len(pnl) < 10:
            continue
        dsr = deflated_sharpe_ratio(pnl, args.freq, int(max(1, n_trials_used)), skew_kurtosis_optional=True)
        lines.append(
            f"- **{name}**: raw_sr={dsr.get('raw_sr', np.nan):.4f}  deflated_sr={dsr.get('deflated_sr', np.nan):.4f}"
        )
    # HAC inference for mean return (first portfolio)
    hac_lags_used: int | None = getattr(args, "_hac_lags_int", None)
    t_hac_mean_return: float | None = None
    p_hac_mean_return: float | None = None
    hac_result: dict = {}
    if portfolio_pnls:
        first_pnl = next(iter(portfolio_pnls.values()))
        hac_result = hac_mean_inference(first_pnl.values, L=hac_lags_used)
        hac_lags_used = hac_result.get("hac_lags_used")
        if hac_result.get("hac_skipped_reason"):
            t_hac_mean_return = None
            p_hac_mean_return = None
        else:
            t_hac_mean_return = hac_result.get("t_hac")
            p_hac_mean_return = hac_result.get("p_hac")
        if hac_result.get("hac_skipped_reason"):
            lines.append(f"HAC mean return: skipped ({hac_result['hac_skipped_reason']})")
        elif t_hac_mean_return is not None and p_hac_mean_return is not None:
            lines.append(
                f"HAC mean return: t_hac={t_hac_mean_return:.4f}  p_hac={p_hac_mean_return:.4f}  (lags={hac_lags_used})"
            )
    # CSCV PBO (when J>=2 and T sufficient)
    pbo_cscv_result: dict = {}
    if len(portfolio_pnls) >= 2:
        try:
            common_idx = None
            for pnl in portfolio_pnls.values():
                idx = pnl.dropna().index
                common_idx = idx if common_idx is None else common_idx.intersection(idx)
            if common_idx is not None and len(common_idx) >= 8:
                R_cscv = pd.DataFrame({k: v.reindex(common_idx) for k, v in portfolio_pnls.items()}).dropna(how="any")
                if R_cscv.shape[1] >= 2 and R_cscv.shape[0] >= 8:
                    pbo_cscv_result = pbo_cscv(
                        R_cscv.values,
                        S=getattr(args, "pbo_cscv_blocks", 16),
                        seed=getattr(args, "rc_seed", 42),
                        max_splits=getattr(args, "pbo_cscv_max_splits", 20000),
                        metric=getattr(args, "pbo_metric", "mean"),
                    )
        except Exception:
            pass
    if pbo_cscv_result and "pbo_cscv_skipped_reason" not in pbo_cscv_result:
        lines.append(
            f"PBO (CSCV): {pbo_cscv_result.get('pbo_cscv', np.nan)}  "
            f"(blocks={pbo_cscv_result.get('n_blocks')}, splits={pbo_cscv_result.get('n_splits')}, "
            f"metric={getattr(args, 'pbo_metric', 'mean')})"
        )
    elif pbo_cscv_result and pbo_cscv_result.get("pbo_cscv_skipped_reason"):
        lines.append(f"PBO (CSCV): skipped ({pbo_cscv_result['pbo_cscv_skipped_reason']})")
    # stats_overview.json (audit: n_trials, HAC, PBO CSCV, RW)
    hac_skipped_reason = hac_result.get("hac_skipped_reason") if portfolio_pnls else None
    rw_enabled = os.environ.get("CRYPTO_ANALYZER_ENABLE_ROMANOWOLF", "").strip() == "1"
    stats_overview = {
        "n_trials_used": n_trials_used,
        "n_trials_user": n_trials_user,
        "n_trials_eff_eigen": n_trials_eff_eigen,
        "n_trials_eff_inputs_total": n_trials_eff_inputs_total,
        "n_trials_eff_inputs_used": n_trials_eff_inputs_used,
        "hac_lags_used": hac_lags_used,
        "hac_skipped_reason": hac_skipped_reason,
        "t_hac_mean_return": t_hac_mean_return,
        "p_hac_mean_return": p_hac_mean_return,
        "rw_enabled": rw_enabled,
    }
    if pbo_cscv_result and "pbo_cscv_skipped_reason" not in pbo_cscv_result:
        stats_overview["pbo_cscv"] = pbo_cscv_result.get("pbo_cscv")
        stats_overview["pbo_cscv_blocks"] = pbo_cscv_result.get("n_blocks")
        stats_overview["pbo_cscv_total_splits"] = pbo_cscv_result.get("pbo_cscv_total_splits")
        stats_overview["pbo_cscv_splits_used"] = pbo_cscv_result.get("n_splits")
        stats_overview["pbo_metric"] = getattr(args, "pbo_metric", "mean")
    elif pbo_cscv_result and pbo_cscv_result.get("pbo_cscv_skipped_reason"):
        stats_overview["pbo_cscv_skipped_reason"] = pbo_cscv_result["pbo_cscv_skipped_reason"]
    # Break diagnostics (run before writing stats_overview so we can set break_diagnostics_written)
    break_result: dict = {}
    break_diagnostics_written = False
    break_diagnostics_skipped_reason: str | None = None
    try:
        from crypto_analyzer.structural_breaks import run_break_diagnostics

        break_series = {}
        if portfolio_pnls:
            first_pnl = next(iter(portfolio_pnls.values()))
            break_series["net_returns"] = first_pnl
        if rc_ic_series_by_hypothesis:
            first_ic = next(iter(rc_ic_series_by_hypothesis.values()))
            if first_ic is not None and not first_ic.empty:
                break_series["ic_series"] = first_ic
        if break_series:
            break_result = run_break_diagnostics(
                break_series,
                hac_lags=getattr(args, "_hac_lags_int", None),
            )
            if break_result.get("series"):
                break_diagnostics_written = True
            else:
                break_diagnostics_skipped_reason = "no series with sufficient data"
        else:
            break_diagnostics_skipped_reason = "no portfolio or IC series"
    except Exception as e:
        break_diagnostics_skipped_reason = str(e)
        # Log so failures are visible; report continues and reason is in stats_overview
        print("Break diagnostics skip:", e)
    stats_overview["break_diagnostics_written"] = break_diagnostics_written
    if break_diagnostics_skipped_reason is not None:
        stats_overview["break_diagnostics_skipped_reason"] = break_diagnostics_skipped_reason
    stats_overview["non_monotone_capacity_curve_observed"] = non_monotone_capacity_curve_observed
    stats_overview["capacity_curve_written"] = capacity_curve_written
    ensure_dir(out_dir)
    stats_overview_path = out_dir / "stats_overview.json"
    write_json_sorted(stats_overview, stats_overview_path)
    bundle_output_paths.append(str(stats_overview_path))
    if break_result.get("series"):
        break_path = out_dir / "break_diagnostics.json"
        write_json_sorted(break_result, break_path)
        bundle_output_paths.append(str(break_path))
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

    # ---- Multi-factor OLS (before report so case-study renderer can use canonical_metrics) ----
    mf_metrics: dict = {}
    try:
        if factor_run_loaded is not None:
            betas_dict, r2_mf, _resid_mf = factor_run_loaded
            if "BTC_spot" in betas_dict and not betas_dict["BTC_spot"].empty:
                mf_metrics["beta_btc_mean"] = float(betas_dict["BTC_spot"].mean(skipna=True).mean())
            if "ETH_spot" in betas_dict and not betas_dict["ETH_spot"].empty:
                mf_metrics["beta_eth_mean"] = float(betas_dict["ETH_spot"].mean(skipna=True).mean())
            if not r2_mf.empty:
                mf_metrics["r2_mean"] = float(r2_mf.mean(skipna=True).mean())
        else:
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

    # ---- Canonical metrics (before report write for case-study renderer) ----
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

    # ---- Write report (standard or case-study) ----
    report_path = out_dir / timestamped_filename("research_v2", "md", sep="_")
    if getattr(args, "case_study", None) == "liqshock":
        import importlib.util

        _renderer_path = Path(__file__).resolve().parent / "case_study_liqshock_renderer.py"
        _spec = importlib.util.spec_from_file_location("case_study_liqshock_renderer", _renderer_path)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        report_md = _mod.render_case_study_liqshock(
            args=args,
            returns_df=returns_df,
            signals_dict=signals_dict,
            orth_dict=orth_dict,
            portfolio_pnls=portfolio_pnls,
            canonical_metrics=canonical_metrics,
            liquidity_panel=liquidity_panel,
            roll_vol_panel=roll_vol_panel,
            bars_match_n_ret=bars_match_n_ret,
            bars_match_n_match=bars_match_n_match,
            bars_match_pct=bars_match_pct,
            run_id=run_id_early,
            out_dir=out_dir,
            rc_result=_rc_result,
            regime_run_id=regime_run_id_early,
            regime_coverage_rel_path=_regime_coverage_rel_path,
            top10_p10_liq_floor=getattr(args, "top10_p10_liq_floor", 250000),
        )
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_md)
    else:
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
            manifest["run_key"] = _run_key_early
            manifest["run_instance_id"] = run_id_early
            manifest["dataset_id_v1"] = _computed_dataset_id_early
            manifest["dataset_id_v2"] = _dataset_id_v2_early
            manifest["dataset_hash_algo"] = _dataset_hash_meta_early.get("dataset_hash_algo", "sqlite_logical_v2")
            manifest["dataset_hash_mode"] = _dataset_hash_meta_early.get("dataset_hash_mode", "STRICT")
            manifest["dataset_hash_scope"] = _dataset_hash_meta_early.get("dataset_hash_scope", [])
            manifest["engine_version"] = _engine_version_early
            manifest["config_version"] = config_hash_early
            manifest["research_spec_version"] = _RESEARCH_SPEC_VERSION
            save_manifest(str(out_dir), manifest)
        except Exception as e:
            print("Manifest skip:", e)

    # ---- SQLite experiment registry (canonical_metrics built before report write) ----
    try:
        from crypto_analyzer.spec import RESEARCH_SPEC_VERSION

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
            "run_key": _run_key_early,
            "dataset_id_v2": _dataset_id_v2_early,
            "dataset_hash_algo": _dataset_hash_meta_early.get("dataset_hash_algo", "sqlite_logical_v2"),
            "dataset_hash_mode": _dataset_hash_meta_early.get("dataset_hash_mode", "STRICT"),
            "engine_version": _engine_version_early,
            "config_version": config_hash_early,
            "research_spec_version": _RESEARCH_SPEC_VERSION,
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
                with sqlite3.connect(experiment_db_path) as conn:
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
            except Exception as sweep_err:
                print("Sweep registry skip:", sweep_err)
    except Exception as e:
        print("SQLite experiment registry skip:", e)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
