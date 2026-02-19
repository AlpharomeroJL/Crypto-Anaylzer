"""
Execution boundary (research-only): Signal → OrderIntent.

Defines interfaces/events, not execution. OrderIntent describes desired exposure/weights
only; no venue routing, no broker, no order IDs. A private execution layer can later
implement an ExecutionAdapter that consumes OrderIntents and routes to IBKR/Binance/etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class OrderIntent:
    """
    Paper concept: desired portfolio exposure at a point in time.

    - ts_utc: timestamp for which the intent applies.
    - asset_weights: symbol -> target weight (e.g. {"BTC": 0.5, "ETH": 0.3, "SOL": 0.2}).
    - meta: optional research metadata (hypothesis_id, run_id, etc.). No venue/order fields.
    """

    ts_utc: str
    asset_weights: Dict[str, float] = field(default_factory=dict)
    meta: Optional[Dict[str, Any]] = None

    def total_weight(self) -> float:
        """Sum of asset weights (for sanity checks)."""
        return sum(self.asset_weights.values())


def signal_to_order_intent(
    asset_weights: Dict[str, float],
    ts_utc: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> OrderIntent:
    """
    Map research signal (target weights) to an OrderIntent.

    Research-only: no order submission, no broker, no routing.
    """
    if ts_utc is None:
        ts_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return OrderIntent(ts_utc=ts_utc, asset_weights=dict(asset_weights), meta=meta or None)
