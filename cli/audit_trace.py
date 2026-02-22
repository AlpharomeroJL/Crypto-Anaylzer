"""
Read-only audit CLI: trace acceptance provenance from DB.
No writes, no migrations, no promotion actions.
Usage: python cli/audit_trace.py trace-acceptance --db <path> --candidate-id <id> [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Repo root for imports
_here = Path(__file__).resolve().parent
_root = _here.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import sqlite3

from crypto_analyzer.governance.audit import trace_acceptance


def _get_db_path(args: argparse.Namespace) -> str:
    if getattr(args, "db", None):
        return args.db
    return os.environ.get("CRYPTO_ANALYZER_DB_PATH", str(Path("reports") / "crypto_analyzer.db"))


def cmd_trace_acceptance(args: argparse.Namespace) -> int:
    """Print audit trace for an accepted/candidate ID (read-only)."""
    db_path = _get_db_path(args)
    candidate_id = getattr(args, "candidate_id", None) or getattr(args, "id", None)
    if not candidate_id:
        print("trace-acceptance requires --candidate-id", file=sys.stderr)
        return 1
    if not Path(db_path).is_file():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        trace = trace_acceptance(conn, candidate_id)
    finally:
        conn.close()

    out = {
        "candidate_id": trace.candidate_id,
        "eligibility_report_id": trace.eligibility_report_id,
        "governance_events": trace.governance_events,
        "artifact_lineage": trace.artifact_lineage,
    }

    if getattr(args, "json", False):
        # Serialize for JSON (sqlite3.Row -> dict already)
        def _serialize(obj):
            if isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_serialize(x) for x in obj]
            if hasattr(obj, "keys"):
                return dict(obj)
            return obj

        print(json.dumps(_serialize(out), indent=2, default=str))
    else:
        print(f"Candidate ID: {trace.candidate_id}")
        print(f"Eligibility report ID: {trace.eligibility_report_id}")
        print(f"Governance events: {len(trace.governance_events)}")
        print(f"Artifact lineage rows: {len(trace.artifact_lineage)}")
        for ev in trace.governance_events[:5]:
            print(f"  - {ev.get('timestamp')} {ev.get('action')} {ev.get('actor')}")
        if trace.artifact_lineage:
            for row in trace.artifact_lineage[:5]:
                aid = row.get("artifact_id", "")
                print(f"  lineage: {aid} {row.get('artifact_type', '')}")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only audit trace (no writes)")
    sub = ap.add_subparsers(dest="command", required=True)

    p_trace = sub.add_parser("trace-acceptance", help="Trace acceptance provenance for a candidate")
    p_trace.add_argument("--db", default=None, help="SQLite DB path")
    p_trace.add_argument("--candidate-id", dest="candidate_id", required=True, help="promotion_candidates.candidate_id")
    p_trace.add_argument("--json", action="store_true", help="Output full trace as JSON")
    p_trace.set_defaults(run=cmd_trace_acceptance)

    args = ap.parse_args()
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
