"""Execution evidence: validate_required (hard fail) and from_dict/to_dict."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from crypto_analyzer.promotion.execution_evidence import (
    ExecutionEvidence,
    execution_evidence_from_json,
    execution_evidence_to_json,
)


def test_validate_required_fails_missing_capacity_curve_path():
    ev = ExecutionEvidence(
        max_participation_rate=10.0,
        cost_config={"fee_bps": 30, "slippage_bps": 10},
        capacity_curve_path=None,
    )
    assert "capacity_curve_path" in ev.validate_required()


def test_validate_required_fails_missing_max_participation_rate():
    ev = ExecutionEvidence(
        capacity_curve_path="csv/cap.csv",
        cost_config={"fee_bps": 30, "slippage_bps": 10},
        max_participation_rate=None,
    )
    assert "max_participation_rate" in ev.validate_required()


def test_validate_required_fails_missing_cost_config():
    ev = ExecutionEvidence(
        capacity_curve_path="csv/cap.csv",
        max_participation_rate=10.0,
        cost_config=None,
    )
    assert "cost_config" in ev.validate_required()


def test_validate_required_fails_cost_config_missing_fee_slippage():
    ev = ExecutionEvidence(
        capacity_curve_path="csv/cap.csv",
        max_participation_rate=10.0,
        cost_config={},
    )
    assert "cost_config" in ev.validate_required()
    ev2 = ExecutionEvidence(
        capacity_curve_path="csv/cap.csv",
        max_participation_rate=10.0,
        cost_config={"fee_bps": 30},
    )
    assert "cost_config" in ev2.validate_required(base_path=None)


def test_validate_required_passes_when_all_present_no_base_path():
    ev = ExecutionEvidence(
        capacity_curve_path="csv/cap.csv",
        max_participation_rate=10.0,
        cost_config={"fee_bps": 30, "slippage_bps": 10},
    )
    assert ev.validate_required(base_path=None) == []


def test_validate_required_fails_when_file_missing_with_base_path():
    ev = ExecutionEvidence(
        capacity_curve_path="csv/cap.csv",
        max_participation_rate=10.0,
        cost_config={"fee_bps": 30, "slippage_bps": 10},
    )
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "csv").mkdir()
        # no cap.csv -> missing
        assert "capacity_curve_path" in ev.validate_required(base_path=base)


def test_validate_required_passes_when_file_exists_readable():
    ev = ExecutionEvidence(
        capacity_curve_path="csv/cap.csv",
        max_participation_rate=10.0,
        cost_config={"fee_bps": 30, "slippage_bps": 10},
    )
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "csv").mkdir()
        (base / "csv" / "cap.csv").write_text("notional_multiplier,sharpe_annual\n1,0.5\n")
        assert ev.validate_required(base_path=base) == []


def test_from_dict_to_dict_roundtrip():
    ev = ExecutionEvidence(
        min_liquidity_usd=1e6,
        max_participation_rate=10.0,
        capacity_curve_path="csv/cap.csv",
        cost_config={"fee_bps": 30, "slippage_bps": 10},
        notes="test",
    )
    d = ev.to_dict()
    ev2 = ExecutionEvidence.from_dict(d)
    assert ev2.capacity_curve_path == ev.capacity_curve_path
    assert ev2.max_participation_rate == ev.max_participation_rate
    assert ev2.cost_config == ev.cost_config
    assert ev2.min_liquidity_usd == ev.min_liquidity_usd


def test_execution_evidence_json_roundtrip():
    ev = ExecutionEvidence(
        max_participation_rate=5.0,
        capacity_curve_path="csv/cap.csv",
        cost_config={"fee_bps": 30, "slippage_bps": 10},
    )
    s = execution_evidence_to_json(ev)
    parsed = json.loads(s)
    assert "capacity_curve_path" in parsed
    assert "cost_config" in parsed
    ev2 = execution_evidence_from_json(s)
    assert ev2.capacity_curve_path == ev.capacity_curve_path
    assert ev2.cost_config == ev.cost_config
