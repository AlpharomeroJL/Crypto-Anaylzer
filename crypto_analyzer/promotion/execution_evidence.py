"""
Execution evidence for promotion: capacity curve, participation cap, cost config.
Phase 3 PR2: required vs soft validation; no new dependencies.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ExecutionEvidence:
    """
    Evidence for execution realism gates. Required (hard fail) when gate is on:
    capacity_curve_path (present + readable), max_participation_rate, cost_config.
    """

    min_liquidity_usd: Optional[float] = None
    max_participation_rate: Optional[float] = None
    spread_model: Optional[Dict[str, Any]] = None
    impact_model: Optional[Dict[str, Any]] = None
    capacity_curve_path: Optional[str] = None
    cost_config: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None

    def validate_required(self, base_path: Optional[Path] = None) -> List[str]:
        """
        Return list of missing required item names (hard fail). Empty list = pass.
        When base_path is set, capacity_curve_path must resolve to an existing readable file.
        """
        missing: List[str] = []
        if not self.capacity_curve_path or not (self.capacity_curve_path or "").strip():
            missing.append("capacity_curve_path")
        elif base_path is not None:
            resolved = (base_path / self.capacity_curve_path.strip()).resolve()
            if not resolved.is_file():
                missing.append("capacity_curve_path")
            else:
                try:
                    resolved.read_text(encoding="utf-8")
                except OSError:
                    missing.append("capacity_curve_path")
        if self.max_participation_rate is None:
            missing.append("max_participation_rate")
        if not self.cost_config or not isinstance(self.cost_config, dict):
            missing.append("cost_config")
        else:
            # Require fee/slippage and spread/impact flags (keys present)
            if "fee_bps" not in self.cost_config or "slippage_bps" not in self.cost_config:
                missing.append("cost_config")
        return missing

    def to_dict(self, float_round: int = 10) -> Dict[str, Any]:
        """Canonical dict with sorted keys; omit None. No new deps."""
        d = asdict(self)
        out: Dict[str, Any] = {}
        for k in sorted(d.keys()):
            v = d[k]
            if v is None:
                continue
            out[k] = _canonical_value(v, float_round)
        return out

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ExecutionEvidence:
        """Build from dict; preserve field names; tolerate extra keys."""
        return cls(
            min_liquidity_usd=_float_or_none(d.get("min_liquidity_usd")),
            max_participation_rate=_float_or_none(d.get("max_participation_rate")),
            spread_model=d.get("spread_model") if isinstance(d.get("spread_model"), dict) else None,
            impact_model=d.get("impact_model") if isinstance(d.get("impact_model"), dict) else None,
            capacity_curve_path=str(d["capacity_curve_path"]) if d.get("capacity_curve_path") is not None else None,
            cost_config=d.get("cost_config") if isinstance(d.get("cost_config"), dict) else None,
            notes=str(d["notes"]) if d.get("notes") is not None else None,
        )


def _float_or_none(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _canonical_value(v: Any, float_round: int) -> Any:
    if isinstance(v, dict):
        return {str(k): _canonical_value(x, float_round) for k, x in sorted(v.items())}
    if isinstance(v, list):
        return [_canonical_value(x, float_round) for x in v]
    if isinstance(v, float):
        return round(v, float_round) if v == v else None
    if isinstance(v, (int, str, bool, type(None))):
        return v
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def execution_evidence_to_json(evidence: ExecutionEvidence, float_round: int = 10) -> str:
    """Stable JSON string (sorted keys)."""
    return json.dumps(evidence.to_dict(float_round=float_round), sort_keys=True)


def execution_evidence_from_json(s: str) -> ExecutionEvidence:
    """Parse JSON string to ExecutionEvidence."""
    return ExecutionEvidence.from_dict(json.loads(s))
