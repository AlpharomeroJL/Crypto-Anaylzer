"""
CLI for promotion workflow: list, create, evaluate.
Phase 3 Slice 5. Opt-in only; no default behavior change.
Usage: python cli/promotion.py list [--db PATH]
       python cli/promotion.py create --from-run RUN_ID --signal NAME --horizon H [--db PATH] [--dataset-id ID] [--config-hash H] [--bundle-path P]
       python cli/promotion.py evaluate --id CANDIDATE_ID [--require-rc] [--db PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

# Repo root for imports
_here = Path(__file__).resolve().parent
_root = _here.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from crypto_analyzer.governance import get_git_commit
from crypto_analyzer.promotion.gating import ThresholdConfig
from crypto_analyzer.promotion.service import evaluate_and_record
from crypto_analyzer.promotion.store_sqlite import (
    create_candidate,
    get_candidate,
    init_promotion_tables,
    list_candidates,
    require_promotion_tables,
)


def _get_db_path(args: argparse.Namespace) -> str:
    if getattr(args, "db", None):
        return args.db
    return os.environ.get("CRYPTO_ANALYZER_DB_PATH", str(Path("reports") / "crypto_analyzer.db"))


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize promotion tables (run Phase 3 migrations). Opt-in only."""
    db = _get_db_path(args)
    if not Path(db).is_file():
        print(f"DB not found: {db}", file=sys.stderr)
        return 1
    init_promotion_tables(db)
    print("Promotion tables initialized (run_migrations_phase3 applied).")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    db = _get_db_path(args)
    if not Path(db).is_file():
        print(f"DB not found: {db}", file=sys.stderr)
        return 1
    conn = sqlite3.connect(db)
    try:
        require_promotion_tables(conn)
        status = getattr(args, "status", None)
        dataset_id = getattr(args, "dataset_id", None) or None
        signal_name = getattr(args, "signal_name", None) or None
        limit = getattr(args, "limit", 100) or 100
        rows = list_candidates(conn, status=status, dataset_id=dataset_id, signal_name=signal_name, limit=limit)
    except RuntimeError as e:
        conn.close()
        print(str(e), file=sys.stderr)
        return 1
    finally:
        conn.close()
    for r in rows:
        print(json.dumps({k: v for k, v in r.items()}, default=str))
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    db = _get_db_path(args)
    run_id = getattr(args, "from_run", None) or getattr(args, "run_id", None)
    signal_name = getattr(args, "signal_name", None)
    horizon = getattr(args, "horizon", None)
    if not run_id or not signal_name or horizon is None:
        print("create requires --from-run, --signal, --horizon", file=sys.stderr)
        return 1
    dataset_id = getattr(args, "dataset_id", None) or ""
    config_hash = getattr(args, "config_hash", None) or ""
    git_commit = get_git_commit()
    bundle_path = getattr(args, "bundle_path", None) or None
    family_id = getattr(args, "family_id", None) or None
    evidence = {}
    if bundle_path:
        evidence["bundle_path"] = bundle_path
        evidence["validation_bundle_path"] = bundle_path
    if family_id:
        evidence["family_id"] = family_id
    if getattr(args, "rc_summary_path", None):
        evidence["rc_summary_path"] = args.rc_summary_path
    exec_ev_path = getattr(args, "execution_evidence_path", None)
    if exec_ev_path:
        evidence["execution_evidence_path"] = exec_ev_path

    evidence_base = None
    if evidence:
        base_arg = getattr(args, "evidence_base_path", None)
        if base_arg:
            evidence_base = Path(base_arg)
        elif bundle_path:
            evidence_base = Path(bundle_path).parent
    conn = sqlite3.connect(db)
    try:
        cid = create_candidate(
            conn,
            dataset_id=dataset_id,
            run_id=run_id,
            signal_name=signal_name,
            horizon=int(horizon),
            config_hash=config_hash,
            git_commit=git_commit,
            family_id=family_id,
            evidence=evidence if evidence else None,
            evidence_base_path=evidence_base,
        )
    except RuntimeError as e:
        conn.close()
        print(str(e), file=sys.stderr)
        return 1
    finally:
        conn.close()
    print(cid)
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    db = _get_db_path(args)
    candidate_id = getattr(args, "id", None) or getattr(args, "candidate_id", None)
    if not candidate_id:
        print("evaluate requires --id CANDIDATE_ID", file=sys.stderr)
        return 1
    if not Path(db).is_file():
        print(f"DB not found: {db}", file=sys.stderr)
        return 1
    require_rc = getattr(args, "require_rc", False)
    max_rc_p = getattr(args, "max_rc_p_value", 0.05)
    require_exec = getattr(args, "require_exec", False)
    min_liq = getattr(args, "min_liquidity_usd", None)
    max_part = getattr(args, "max_participation", None)
    allow_missing_exec = getattr(args, "allow_missing_exec", False)
    thresholds = ThresholdConfig(
        require_reality_check=require_rc,
        max_rc_p_value=max_rc_p,
        require_execution_evidence=require_exec,
        min_liquidity_usd_min=min_liq,
        max_participation_rate_max=max_part,
    )
    conn = sqlite3.connect(db)
    try:
        row = get_candidate(conn, candidate_id)
        if not row:
            print(f"Candidate not found: {candidate_id}", file=sys.stderr)
            return 1
        evidence = json.loads(row["evidence_json"]) if row.get("evidence_json") else {}
        bundle_path = evidence.get("bundle_path") or evidence.get("validation_bundle_path")
        base = Path(bundle_path).parent if bundle_path else None
        current_status = (row.get("status") or "exploratory").strip()
        target_status = "candidate" if current_status == "exploratory" else "accepted"
        decision = evaluate_and_record(
            conn,
            candidate_id,
            thresholds,
            bundle_path or "",
            evidence_base_path=base,
            target_status=target_status,
            allow_missing_execution_evidence=allow_missing_exec,
        )
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    finally:
        conn.close()
    out = {"status": decision.status, "reasons": decision.reasons, "metrics_snapshot": decision.metrics_snapshot}
    if getattr(decision, "warnings", None):
        out["warnings"] = decision.warnings
    print(json.dumps(out))
    return 0 if decision.status == "accepted" else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Promotion workflow CLI (Phase 3 Slice 5)")
    ap.add_argument(
        "--db", default=None, help="SQLite DB path (default: CRYPTO_ANALYZER_DB_PATH or reports/crypto_analyzer.db)"
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize promotion tables (run Phase 3 migrations)")
    p_init.set_defaults(run=cmd_init)

    p_list = sub.add_parser("list", help="List candidates")
    p_list.add_argument("--status", choices=["exploratory", "candidate", "accepted", "rejected"], default=None)
    p_list.add_argument("--dataset-id", default=None)
    p_list.add_argument("--signal-name", default=None)
    p_list.add_argument("--limit", type=int, default=100)
    p_list.set_defaults(run=cmd_list)

    p_create = sub.add_parser("create", help="Create candidate from run")
    p_create.add_argument("--from-run", dest="from_run", required=True, help="run_id from reportv2")
    p_create.add_argument("--signal", dest="signal_name", required=True)
    p_create.add_argument("--horizon", type=int, required=True)
    p_create.add_argument("--dataset-id", default=None)
    p_create.add_argument("--config-hash", default=None)
    p_create.add_argument("--bundle-path", default=None, help="Path to ValidationBundle JSON")
    p_create.add_argument("--family-id", default=None)
    p_create.add_argument("--rc-summary-path", default=None)
    p_create.add_argument(
        "--execution-evidence-path",
        default=None,
        help="Path to execution_evidence.json (stored relative when --evidence-base-path set)",
    )
    p_create.add_argument("--evidence-base-path", default=None, help="Base path for relativizing evidence paths")
    p_create.set_defaults(run=cmd_create)

    p_eval = sub.add_parser("evaluate", help="Evaluate candidate and record decision")
    p_eval.add_argument("--id", dest="id", required=True, help="candidate_id")
    p_eval.add_argument("--require-rc", dest="require_rc", action="store_true", help="Require Reality Check pass")
    p_eval.add_argument("--max-rc-p-value", type=float, default=0.05)
    p_eval.add_argument(
        "--require-exec",
        dest="require_exec",
        action="store_true",
        help="Require execution evidence (capacity curve, participation cap, cost config)",
    )
    p_eval.add_argument("--min-liquidity-usd", type=float, default=None, help="Min liquidity USD threshold (optional)")
    p_eval.add_argument(
        "--max-participation", type=float, default=None, help="Max participation rate threshold (optional)"
    )
    p_eval.add_argument(
        "--allow-missing-exec",
        dest="allow_missing_exec",
        action="store_true",
        help="Allow promotion without execution evidence (auditable override)",
    )
    p_eval.set_defaults(run=cmd_evaluate)

    args = ap.parse_args()
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
