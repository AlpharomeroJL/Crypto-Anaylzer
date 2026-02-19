"""
ValidationBundle: contract for per-signal validation outputs (IC, decay, turnover, meta).
JSON-serializable; large series stored as artifact CSVs and referenced by path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ValidationBundle:
    """
    Per-signal validation output. IC series stored as CSV artifacts; bundle holds paths and summaries.
    """

    run_id: str
    dataset_id: str
    signal_name: str
    freq: str
    horizons: List[int]
    ic_summary_by_horizon: Dict[int, Dict[str, float]]  # horizon -> {mean_ic, std_ic, t_stat, hit_rate, n_obs}
    ic_decay_table: List[Dict[str, Any]]  # list of dicts for JSON (horizon_bars, mean_ic, std_ic, n_obs, t_stat)
    meta: Dict[str, Any]  # config_hash, git_commit, engine_version, as_of_lag_bars, deterministic_time_used, etc.
    # Artifact paths (relative or absolute) for IC series and decay CSV
    ic_series_path_by_horizon: Dict[int, str] = field(default_factory=dict)
    ic_decay_path: Optional[str] = None
    turnover_path: Optional[str] = None
    gross_returns_path: Optional[str] = None
    net_returns_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe dict with stable key ordering (caller should use sort_keys when writing)."""
        d = asdict(self)
        out: Dict[str, Any] = {}
        for k, v in d.items():
            if isinstance(v, dict):
                # JSON keys must be strings (e.g. ic_summary_by_horizon has int keys)
                out[k] = {str(kk): _round_floats(vv) for kk, vv in v.items()}
            elif isinstance(v, list):
                out[k] = [_round_floats(x) if isinstance(x, dict) else x for x in v]
            elif isinstance(v, float):
                out[k] = _round_floats(v)
            else:
                out[k] = v
        return out


def _round_floats(x: Any, ndigits: int = 10) -> Any:
    if isinstance(x, float):
        return round(x, ndigits) if x == x else None  # preserve NaN as None for JSON
    if isinstance(x, dict):
        return {str(k): _round_floats(v, ndigits) for k, v in x.items()}
    if isinstance(x, list):
        return [_round_floats(i, ndigits) for i in x]
    return x
