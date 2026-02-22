"""
Transform contracts: Exogenous (no fit) vs Trainable (fit on train only).
Registry for attestation of what was applied.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class ExogenousTransform(Protocol):
    """Purely functional, time-local; no fitting, no state. transform(df) -> df_out."""

    def transform(self, df: pd.DataFrame) -> pd.DataFrame: ...


@dataclass
class TrainState:
    """Opaque state produced by TrainableTransform.fit(); consumed by transform(..., state)."""

    _payload: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class TrainableTransform(Protocol):
    """
    Fit on train only; transform using fitted state. Must not read rows outside train during fit.
    """

    def fit(self, train_df: pd.DataFrame) -> TrainState: ...

    def transform(self, df: pd.DataFrame, state: TrainState) -> pd.DataFrame: ...


@dataclass
class TransformSpec:
    """Metadata for attestation: name, kind, version, params_hash."""

    name: str
    kind: str  # "exogenous" | "trainable"
    version: int = 1
    params_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "version": self.version,
            "params_hash": self.params_hash,
        }


# Registry: name -> (spec, implementation). Implementation is ExogenousTransform or TrainableTransform.
TRANSFORM_REGISTRY: Dict[str, tuple[TransformSpec, Any]] = {}
