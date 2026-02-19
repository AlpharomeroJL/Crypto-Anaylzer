"""Tests for execution boundary: OrderIntent and signal_to_order_intent (research-only)."""

from __future__ import annotations

from crypto_analyzer.order_intent import OrderIntent, signal_to_order_intent


def test_order_intent_total_weight():
    intent = OrderIntent(ts_utc="2025-01-01T00:00:00", asset_weights={"BTC": 0.5, "ETH": 0.3, "SOL": 0.2})
    assert intent.total_weight() == 1.0


def test_signal_to_order_intent_default_ts():
    intent = signal_to_order_intent({"BTC": 1.0})
    assert intent.asset_weights == {"BTC": 1.0}
    assert intent.ts_utc is not None
    assert intent.meta is None


def test_signal_to_order_intent_with_meta():
    intent = signal_to_order_intent(
        {"ETH": 0.6, "SOL": 0.4},
        ts_utc="2025-02-01T12:00:00",
        meta={"run_id": "r1"},
    )
    assert intent.asset_weights == {"ETH": 0.6, "SOL": 0.4}
    assert intent.ts_utc == "2025-02-01T12:00:00"
    assert intent.meta == {"run_id": "r1"}
