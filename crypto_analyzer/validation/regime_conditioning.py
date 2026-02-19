"""
Regime-conditioned validation: join regime labels (exact, no leakage), IC summary/decay by regime, coverage.

Join policy: exact on ts_utc only. Regime at t is attached to row t; never use regime at t+1 for t.
See docs/spec/phase3_regimes_slice2_alignment.md.
"""

from __future__ import annotations

from typing import Dict, Literal, Optional

import numpy as np
import pandas as pd


def attach_regime_label(
    frame: pd.DataFrame,
    regimes: pd.DataFrame,
    join_policy: Literal["exact"] = "exact",
) -> pd.DataFrame:
    """
    Attach regime_label to frame by joining on ts_utc. Exact join only: row at t gets regime at t (no t+1).

    frame: must have ts_utc as index or column.
    regimes: must have ts_utc and regime_label (columns or index).
    Missing regime -> regime_label = "unknown".
    Returns frame with regime_label column added, stable-sorted by ts_utc then other columns.
    """
    if frame.empty:
        out = frame.copy()
        out["regime_label"] = pd.Series(dtype=object)
        return out

    # Normalize ts_utc on frame
    if "ts_utc" not in frame.columns and frame.index.name in ("ts_utc", None):
        ts_frame = frame.index
        frame = frame.copy()
    else:
        if "ts_utc" not in frame.columns:
            raise ValueError("frame must have ts_utc as column or index")
        ts_frame = pd.to_datetime(frame["ts_utc"])

    # Normalize regimes
    if regimes.empty:
        out = frame.copy()
        out["regime_label"] = "unknown"
        return _stable_sort(out, ts_frame)

    reg = regimes.copy()
    if "ts_utc" not in reg.columns:
        reg = reg.reset_index()
    reg_ts = pd.to_datetime(reg["ts_utc"])
    reg_label = reg["regime_label"] if "regime_label" in reg.columns else reg.iloc[:, 1]
    reg_series = pd.Series(reg_label.values, index=reg_ts)
    reg_series = reg_series[~reg_series.index.duplicated(keep="first")]

    # Exact join: reindex to frame's ts, fill missing with "unknown"
    aligned = reg_series.reindex(ts_frame)
    aligned = aligned.fillna("unknown").astype(str)
    out = frame.copy()
    out["regime_label"] = aligned.values
    return _stable_sort(out, ts_frame)


def _stable_sort(df: pd.DataFrame, ts_series: pd.Series) -> pd.DataFrame:
    """Sort by ts_utc then by column names for deterministic output."""
    if "ts_utc" in df.columns:
        out = df.sort_values("ts_utc").sort_index(axis=1)
    else:
        out = df.sort_index(axis=0).sort_index(axis=1)
    return out


def ic_summary_by_regime(
    ic_series: pd.Series,
    regime_labels: pd.Series,
    horizon: Optional[int] = None,
    exclude_unknown: bool = True,
) -> pd.DataFrame:
    """
    Per-regime IC summary: mean_ic, std_ic, n_bars, t_stat. One row per regime.

    ic_series: index = ts_utc. regime_labels: same index. Aligned by index.
    exclude_unknown: if True, do not include "unknown" in output (still counted in coverage).
    """
    common = ic_series.index.intersection(regime_labels.index)
    if len(common) == 0:
        return pd.DataFrame(columns=["regime", "horizon", "mean_ic", "std_ic", "n_bars", "t_stat"])
    ic = ic_series.reindex(common).dropna()
    reg = regime_labels.reindex(common).fillna("unknown")
    reg = reg.loc[ic.index]
    if exclude_unknown:
        mask = reg != "unknown"
        ic = ic[mask]
        reg = reg[mask]
    if ic.empty:
        return pd.DataFrame(columns=["regime", "horizon", "mean_ic", "std_ic", "n_bars", "t_stat"])

    rows = []
    for r in sorted(reg.unique()):
        sub = ic[reg == r].dropna()
        n = len(sub)
        if n < 2:
            rows.append(
                {
                    "regime": r,
                    "horizon": horizon,
                    "mean_ic": float(sub.mean()) if n else np.nan,
                    "std_ic": np.nan,
                    "n_bars": n,
                    "t_stat": np.nan,
                }
            )
            continue
        mean_ic = float(sub.mean())
        std_ic = float(sub.std(ddof=1))
        t_stat = (mean_ic / std_ic) * np.sqrt(n) if std_ic and std_ic > 1e-12 else np.nan
        rows.append(
            {"regime": r, "horizon": horizon, "mean_ic": mean_ic, "std_ic": std_ic, "n_bars": n, "t_stat": t_stat}
        )
    return pd.DataFrame(rows)


def ic_summary_by_regime_multi(
    ic_series_by_horizon: Dict[int, pd.Series],
    regime_labels: pd.Series,
    exclude_unknown: bool = True,
) -> pd.DataFrame:
    """
    Per-regime, per-horizon IC summary: regime, horizon, mean_ic, std_ic, n_bars, t_stat.
    One row per (regime, horizon). Uses exact alignment (no leakage).
    """
    rows = []
    for h in sorted(ic_series_by_horizon.keys()):
        ic_s = ic_series_by_horizon[h]
        summary = ic_summary_by_regime(ic_s, regime_labels, horizon=h, exclude_unknown=exclude_unknown)
        rows.append(summary)
    if not rows:
        return pd.DataFrame(columns=["regime", "horizon", "mean_ic", "std_ic", "n_bars", "t_stat"])
    return pd.concat(rows, ignore_index=True)


def ic_decay_by_regime(
    ic_series_by_horizon: Dict[int, pd.Series],
    regime_labels: pd.Series,
    exclude_unknown: bool = True,
) -> pd.DataFrame:
    """
    Per-regime, per-horizon IC summary: regime, horizon_bars, mean_ic, std_ic, n_obs.

    ic_series_by_horizon: {horizon: ic_series with ts_utc index}.
    regime_labels: Series index = ts_utc.
    """
    rows = []
    for h in sorted(ic_series_by_horizon.keys()):
        ic_s = ic_series_by_horizon[h]
        summary = ic_summary_by_regime(ic_s, regime_labels, horizon=h, exclude_unknown=exclude_unknown)
        for _, row in summary.iterrows():
            rows.append(
                {
                    "regime": row["regime"],
                    "horizon_bars": h,
                    "mean_ic": row["mean_ic"],
                    "std_ic": row["std_ic"],
                    "n_obs": int(row["n_bars"]),
                }
            )
    if not rows:
        return pd.DataFrame(columns=["regime", "horizon_bars", "mean_ic", "std_ic", "n_obs"])
    return pd.DataFrame(rows)


def regime_coverage(regime_labels: pd.Series) -> Dict[str, float | int | Dict[str, int]]:
    """
    Coverage summary: pct_available, pct_unknown, n_ts, n_with_regime, n_unknown, regime_distribution.

    regime_labels: Series (index = ts_utc or arbitrary). "unknown" counts as missing for pct_available.
    """
    if regime_labels.empty:
        return {
            "pct_available": 0.0,
            "pct_unknown": 1.0,
            "n_ts": 0,
            "n_with_regime": 0,
            "n_unknown": 0,
            "regime_distribution": {},
        }
    n = len(regime_labels)
    unknown = (regime_labels.fillna("unknown").astype(str) == "unknown").sum()
    n_with_regime = n - int(unknown)
    pct_available = n_with_regime / n if n else 0.0
    pct_unknown = int(unknown) / n if n else 1.0
    dist = regime_labels.fillna("unknown").astype(str).value_counts().sort_index()
    # Sorted by label so artifact and meta["regime_coverage_summary"] are byte-stable
    regime_distribution = dict(sorted((str(k), int(v)) for k, v in dist.items()))
    return {
        "pct_available": float(pct_available),
        "pct_unknown": float(pct_unknown),
        "n_ts": n,
        "n_with_regime": int(n_with_regime),
        "n_unknown": int(unknown),
        "regime_distribution": regime_distribution,
    }
