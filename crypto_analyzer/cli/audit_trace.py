"""
Read-only audit CLI: trace acceptance provenance from DB.
No writes, no migrations, no promotion actions.
Usage: crypto-analyzer audit_trace trace-acceptance --db <path> --candidate-id <id> [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional

from crypto_analyzer.governance.audit import trace_acceptance


def _get_db_path(args: argparse.Namespace) -> str:
    if getattr(args, "db", None):
        return args.db
    return os.environ.get("CRYPTO_ANALYZER_DB_PATH", str(Path("reports") / "crypto_analyzer.db"))


def _get_eligibility_provenance(conn: sqlite3.Connection, eligibility_report_id: str | None) -> dict:
    """Return run_key, dataset_id_v2, engine_version, config_version from eligibility_reports if present."""
    out = {"run_key": "", "dataset_id_v2": "", "engine_version": "", "config_version": "", "seed_version": ""}
    if not eligibility_report_id:
        return out
    cur = conn.execute(
        "SELECT run_key, run_instance_id, dataset_id_v2, engine_version, config_version FROM eligibility_reports WHERE eligibility_report_id = ?",
        (eligibility_report_id,),
    )
    row = cur.fetchone()
    if row:
        out["run_key"] = row[0] or ""
        out["dataset_id_v2"] = row[2] or ""
        out["engine_version"] = row[3] or ""
        out["config_version"] = row[4] or ""
    return out


def cmd_trace_acceptance(args: argparse.Namespace) -> int:
    """Print audit trace for a candidate_id (read-only)."""
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
        cur = conn.execute("SELECT status FROM promotion_candidates WHERE candidate_id = ?", (candidate_id,))
        row = cur.fetchone()
        if not row:
            print(f"Candidate not found: {candidate_id}", file=sys.stderr)
            return 1
        status = (row[0] or "").strip()
        if status != "accepted":
            print(
                f"Candidate is not accepted; status={status!r}. Trace is most meaningful after promotion to accepted.",
                file=sys.stderr,
            )

        trace = trace_acceptance(conn, candidate_id)
        prov = _get_eligibility_provenance(conn, trace.eligibility_report_id)
        run_inst = trace.artifact_lineage[0].get("run_instance_id") if trace.artifact_lineage else ""
        if run_inst:
            cur = conn.execute(
                "SELECT schema_versions_json FROM artifact_lineage WHERE run_instance_id = ? LIMIT 1",
                (run_inst,),
            )
            r = cur.fetchone()
            if r and r[0]:
                try:
                    sv = json.loads(r[0])
                    prov["seed_version"] = str(sv.get("seed_derivation", ""))
                except Exception:
                    pass
    finally:
        conn.close()

    out = {
        "candidate_id": trace.candidate_id,
        "eligibility_report_id": trace.eligibility_report_id,
        "governance_events": trace.governance_events,
        "artifact_lineage": trace.artifact_lineage,
    }

    if getattr(args, "json", False):

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
        print(f"run_key: {prov['run_key'] or '(none)'}")
        print(f"dataset_id_v2: {prov['dataset_id_v2'] or '(none)'}")
        print(f"engine_version: {prov['engine_version'] or '(none)'}")
        print(f"config_version: {prov['config_version'] or '(none)'}")
        print(f"seed_version: {prov['seed_version'] or '(see bundle meta / lineage)'}")
        print(f"Governance events: {len(trace.governance_events)}")
        print(f"Artifact lineage rows: {len(trace.artifact_lineage)}")
        for ev in trace.governance_events[:5]:
            print(f"  - {ev.get('timestamp')} {ev.get('action')} {ev.get('actor')}")
        if trace.artifact_lineage:
            for row in trace.artifact_lineage[:5]:
                aid = row.get("artifact_id", "")
                print(f"  lineage: {aid} {row.get('artifact_type', '')}")

    return 0


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    ap = argparse.ArgumentParser(description="Read-only audit trace (no writes)")
    sub = ap.add_subparsers(dest="command", required=True)

    p_trace = sub.add_parser("trace-acceptance", help="Trace acceptance provenance for a candidate")
    p_trace.add_argument("--db", default=None, help="SQLite DB path")
    p_trace.add_argument("--candidate-id", dest="candidate_id", required=True, help="promotion_candidates.candidate_id")
    p_trace.add_argument("--json", action="store_true", help="Output full trace as JSON")
    p_trace.set_defaults(run=cmd_trace_acceptance)

    args = ap.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
