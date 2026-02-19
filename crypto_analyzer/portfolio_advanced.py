"""
Advanced portfolio construction: constraints, neutralities, diagnostics.
Uses heuristic optimizer (no cvxpy). Research-only.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from .portfolio import beta_neutralize_weights
from .risk_model import ensure_psd


def optimize_long_short_portfolio(
    expected_returns: pd.Series,
    cov: pd.DataFrame,
    constraints: Optional[Dict[str, Any]] = None,
) -> Tuple[pd.Series, Dict[str, Any]]:
    """
    Long/short portfolio from expected returns and covariance. Heuristic:
    rank-based raw weights -> beta neutralization -> risk scaling (inv vol) -> clip -> renormalize.
    Optional cvxpy can be added later for exact QP.

    constraints may include:
      max_weight_per_asset: float
      min_liquidity: pd.Series (asset -> min liquidity; exclude if liquidity < min)
      capacity_usd: pd.Series (asset -> max notional; cap |w_i| * AUM by capacity)
      betas: pd.Series (for beta neutrality to BTC)
      target_beta: float (default 0)
      dollar_neutral: bool (sum weights = 0)
      target_gross_leverage: float (sum |w| = this)
      max_slippage_bps: float
      est_slippage_bps: pd.Series (exclude if est_slippage_bps > max_slippage_bps)
      liquidity_usd: pd.Series (for min_liquidity filter)

    Returns (weights, diagnostics).
    """
    constraints = constraints or {}
    if expected_returns.empty:
        return pd.Series(dtype=float), _empty_diagnostics()

    # Align
    assets = expected_returns.index.intersection(cov.index) if not cov.empty else expected_returns.index
    assets = assets.intersection(cov.columns) if not cov.empty else assets
    if len(assets) == 0:
        return pd.Series(dtype=float), _empty_diagnostics()

    er = expected_returns.reindex(assets).fillna(0)
    cov_aligned = cov.reindex(index=assets, columns=assets).fillna(0) if not cov.empty else pd.DataFrame()
    cov_psd = ensure_psd(cov_aligned) if not cov_aligned.empty else pd.DataFrame()

    # 1) Raw weights from rank (long positive alpha, short negative)
    ranks = er.rank(method="average", pct=True)
    raw = (ranks - 0.5) * 2.0  # roughly in [-1, 1]
    raw = raw.fillna(0)

    # 2) Exclusions
    max_slip = constraints.get("max_slippage_bps")
    est_slip = constraints.get("est_slippage_bps")
    if max_slip is not None and est_slip is not None:
        if hasattr(est_slip, "reindex"):
            exclude_slip = est_slip.reindex(assets).fillna(np.inf) > max_slip
            raw.loc[exclude_slip[exclude_slip].index] = 0

    min_liq = constraints.get("min_liquidity")
    liq_series = constraints.get("liquidity_usd")
    if min_liq is not None and liq_series is not None and hasattr(liq_series, "reindex"):
        liq = liq_series.reindex(assets).fillna(0)
        raw.loc[liq < min_liq] = 0

    # 3) Beta neutrality
    betas = constraints.get("betas")
    target_beta = constraints.get("target_beta", 0.0)
    if betas is not None and not betas.empty:
        raw = beta_neutralize_weights(raw, betas, target_beta=target_beta)
        raw = raw.reindex(assets).fillna(0)

    # 4) Risk scaling: inverse vol from diagonal of cov
    if not cov_psd.empty:
        vol = np.sqrt(np.diag(cov_psd.values))
        vol = np.where(vol > 1e-12, vol, np.nan)
        inv_vol = pd.Series(np.where(np.isfinite(vol), 1.0 / vol, 0), index=assets)
        raw = raw * inv_vol
    raw = raw.fillna(0)

    # 5) Max weight and capacity cap
    max_w = constraints.get("max_weight_per_asset")
    if max_w is not None:
        raw = raw.clip(lower=-float(max_w), upper=float(max_w))
    cap = constraints.get("capacity_usd")
    if cap is not None and hasattr(cap, "reindex"):
        # Capacity cap: scale down weight so |w_i| * notional doesn't exceed capacity_i. We don't have AUM here; use relative cap: w_i capped by cap_i / sum(cap) proxy.
        cap_s = cap.reindex(assets).fillna(0)
        if cap_s.abs().sum() > 0:
            cap_pct = cap_s / cap_s.abs().sum()
            # Limit |w_i| to not exceed some multiple of cap share (e.g. 2x cap share)
            cap_limit = cap_pct * 2.0
            raw = raw.clip(lower=-cap_limit, upper=cap_limit)

    # 6) Dollar neutral
    if constraints.get("dollar_neutral", True):
        s = raw.sum()
        if abs(s) > 1e-12:
            n = (raw != 0).sum() or 1
            raw = raw - s / n

    # 7) Target gross leverage
    gross_target = constraints.get("target_gross_leverage")
    if gross_target is not None and gross_target > 0:
        gross = raw.abs().sum()
        if gross > 1e-12:
            raw = raw * (gross_target / gross)

    # Final clip and diagnostics
    if max_w is not None:
        raw = raw.clip(lower=-float(max_w), upper=float(max_w))
    w = raw

    # Diagnostics
    port_beta = float((w * betas.reindex(assets).fillna(0)).sum()) if betas is not None else np.nan
    gross = float(w.abs().sum())
    net = float(w.sum())
    n_assets = int((w != 0).sum())
    top = w.nlargest(5)
    bot = w.nsmallest(5)
    diagnostics = {
        "achieved_beta": port_beta,
        "gross_leverage": gross,
        "net_exposure": net,
        "n_assets": n_assets,
        "top_long": top.to_dict(),
        "top_short": bot.to_dict(),
    }
    return w, diagnostics


def _empty_diagnostics() -> Dict[str, Any]:
    return {
        "achieved_beta": np.nan,
        "gross_leverage": 0.0,
        "net_exposure": 0.0,
        "n_assets": 0,
        "top_long": {},
        "top_short": {},
    }
