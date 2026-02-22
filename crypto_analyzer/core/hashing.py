"""
Canonical hashing primitives: file SHA256 and stable JSON helpers.
Façade over crypto_analyzer.artifacts; do not change JSON encoding semantics.
"""

from __future__ import annotations

from crypto_analyzer.artifacts import compute_file_sha256

# TODO: stable_json_dumps — no standalone function in codebase; artifacts has write_json_sorted (writes to file).
# TODO: canonical_json_bytes — no standalone function in codebase; promotion/store_sqlite has _canonical_json (private).

__all__ = ["compute_file_sha256"]
