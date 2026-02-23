"""
Stable facade: run identity (manifests, run_key, git) + promotion entrypoint (evaluate_and_record, promote).
Phase 3 A3. Intentionally imports core.run_identity, timeutils, and .promote (promotion is part of this facade).
Does not import cli. Do not add exports without updating __all__.
"""

from __future__ import annotations

from crypto_analyzer.core.run_identity import (
    RunIdentity,
    append_run_registry,
    build_run_identity,
    compute_run_key,
    get_env_fingerprint,
    get_git_commit,
    load_manifests,
    make_run_manifest,
    save_manifest,
    stable_run_id,
)
from crypto_analyzer.timeutils import now_utc_iso

from .promote import evaluate_and_record, promote

# Do not add exports without updating __all__.
__all__ = [
    "RunIdentity",
    "append_run_registry",
    "build_run_identity",
    "compute_run_key",
    "evaluate_and_record",
    "get_env_fingerprint",
    "get_git_commit",
    "load_manifests",
    "make_run_manifest",
    "now_utc_iso",
    "promote",
    "save_manifest",
    "stable_run_id",
]
