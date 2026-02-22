"""
Explicit run and execution context for pipelines and reportv2.
Phase 3.5 A2. Replaces scattered provenance dicts; required for artifact writing and stochastic paths.
Core-only: no imports from governance, store, or cli.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Union


@dataclass(frozen=True)
class RunContext:
    """
    Reproducibility and audit identity for a single run.
    Any code writing artifacts or invoking stochastic procedures must receive this (not raw dicts).
    """

    run_key: str
    run_instance_id: str
    dataset_id_v2: str
    engine_version: str = ""
    config_version: Optional[str] = ""
    seed_version: int = 1
    schema_versions: Dict[str, Any] = field(default_factory=dict)

    def require_for_promotion(self) -> None:
        """Raise ValueError with actionable message if context is missing fields required for candidate/accepted."""
        if not (self.run_key and self.run_key.strip()):
            raise ValueError("RunContext.run_key is required for promotion (candidate/accepted)")
        if not (self.dataset_id_v2 and str(self.dataset_id_v2).strip()):
            raise ValueError("RunContext.dataset_id_v2 is required for promotion")
        if not (self.engine_version is not None and str(self.engine_version).strip()):
            raise ValueError("RunContext.engine_version is required for promotion")
        if self.config_version is None or (isinstance(self.config_version, str) and not self.config_version.strip()):
            raise ValueError("RunContext.config_version is required for promotion")


@dataclass
class ExecContext:
    """
    Execution environment: output directory, backend, optional DB connection/path.
    Used across CLI and pipeline paths.
    """

    out_dir: Union[str, Path]
    backend: str = "sqlite"
    db_path: Optional[Union[str, Path]] = None
    conn: Any = None
    deterministic_time: bool = True
