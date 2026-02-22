"""
Phase 3 schema migrations: regime_runs, regime_states, promotion_candidates, promotion_events.

NOT applied by default. Call run_migrations_phase3(conn, db_path) only when
caller explicitly opts in (e.g. CRYPTO_ANALYZER_ENABLE_REGIMES=1 or promotion workflow).
Do not import this module from run_migrations() or run_migrations_v2().

Backup/restore: same discipline as v2 (shutil.copy2 before apply, restore on
failure). Version numbers are in a phase3-only namespace (1..5) tracked in
schema_migrations_phase3; idempotent CREATE TABLE IF NOT EXISTS and version check.
See docs/spec/components/schema_plan.md and phase3_promotion_slice5_alignment.md.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from pathlib import Path
from typing import Callable, List, Tuple

from crypto_analyzer.core.run_identity import get_git_commit
from crypto_analyzer.timeutils import now_utc_iso

logger = logging.getLogger(__name__)

Migration = Tuple[int, str, Callable[[sqlite3.Connection], None]]


def _phase3_migration_001_schema_migrations_phase3(conn: sqlite3.Connection) -> None:
    """Create schema_migrations_phase3 table to track Phase 3 migrations only."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations_phase3 (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at_utc TEXT NOT NULL,
            git_commit TEXT
        );
        """
    )
    conn.commit()


def _phase3_migration_002_regime_runs(conn: sqlite3.Connection) -> None:
    """Create regime_runs table per schema_plan.md."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS regime_runs (
            regime_run_id TEXT PRIMARY KEY,
            created_at_utc TEXT NOT NULL,
            dataset_id TEXT NOT NULL,
            freq TEXT NOT NULL,
            model TEXT NOT NULL,
            params_json TEXT
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_regime_runs_dataset_freq ON regime_runs(dataset_id, freq);")
    conn.commit()


def _phase3_migration_003_regime_states(conn: sqlite3.Connection) -> None:
    """Create regime_states table per schema_plan.md."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS regime_states (
            regime_run_id TEXT NOT NULL,
            ts_utc TEXT NOT NULL,
            regime_label TEXT NOT NULL,
            regime_prob REAL,
            PRIMARY KEY (regime_run_id, ts_utc)
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_regime_states_ts ON regime_states(regime_run_id, ts_utc);")
    conn.commit()


def _phase3_migration_004_promotion_candidates(conn: sqlite3.Connection) -> None:
    """Create promotion_candidates table per phase3_promotion_slice5_alignment.md."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS promotion_candidates (
            candidate_id TEXT PRIMARY KEY,
            created_at_utc TEXT NOT NULL,
            status TEXT NOT NULL,
            dataset_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            family_id TEXT,
            signal_name TEXT NOT NULL,
            horizon INTEGER NOT NULL,
            estimator TEXT,
            config_hash TEXT NOT NULL,
            git_commit TEXT NOT NULL,
            notes TEXT,
            evidence_json TEXT
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_promotion_candidates_status ON promotion_candidates(status);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_promotion_candidates_dataset ON promotion_candidates(dataset_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_promotion_candidates_signal ON promotion_candidates(signal_name);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_promotion_candidates_created ON promotion_candidates(created_at_utc);")
    conn.commit()


def _phase3_migration_005_promotion_events(conn: sqlite3.Connection) -> None:
    """Create promotion_events table (append-only audit) per phase3_promotion_slice5_alignment.md."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS promotion_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT NOT NULL,
            ts_utc TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_promotion_events_candidate ON promotion_events(candidate_id);")
    conn.commit()


def _phase3_migration_006_sweep_families(conn: sqlite3.Connection) -> None:
    """Create sweep_families table (Phase 3 sweep registry hardening). Opt-in via run_migrations_phase3."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sweep_families (
            family_id TEXT PRIMARY KEY,
            created_at_utc TEXT NOT NULL,
            dataset_id TEXT NOT NULL,
            run_id TEXT,
            sweep_name TEXT,
            sweep_payload_json TEXT NOT NULL,
            git_commit TEXT,
            config_hash TEXT
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sweep_families_dataset ON sweep_families(dataset_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sweep_families_created ON sweep_families(created_at_utc);")
    conn.commit()


def _phase3_migration_007_sweep_hypotheses(conn: sqlite3.Connection) -> None:
    """Create sweep_hypotheses table (Phase 3 sweep registry). One row per hypothesis in a family."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sweep_hypotheses (
            family_id TEXT NOT NULL,
            hypothesis_id TEXT NOT NULL,
            signal_name TEXT NOT NULL,
            horizon INTEGER NOT NULL,
            estimator TEXT,
            params_json TEXT,
            regime_run_id TEXT,
            PRIMARY KEY (family_id, hypothesis_id)
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sweep_hypotheses_signal ON sweep_hypotheses(signal_name);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sweep_hypotheses_horizon ON sweep_hypotheses(horizon);")
    conn.commit()


def _phase3_migration_008_eligibility_reports(conn: sqlite3.Connection) -> None:
    """Phase 1: Create eligibility_reports table for non-bypassable governance."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS eligibility_reports (
            eligibility_report_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL,
            level TEXT NOT NULL CHECK(level IN ('exploratory','candidate','accepted')),
            passed INTEGER NOT NULL CHECK(passed IN (0,1)),
            blockers_json TEXT NOT NULL,
            warnings_json TEXT NOT NULL,
            computed_at_utc TEXT NOT NULL,
            run_key TEXT,
            run_instance_id TEXT,
            dataset_id_v2 TEXT,
            engine_version TEXT,
            config_version TEXT
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_eligibility_reports_candidate ON eligibility_reports(candidate_id);")
    conn.commit()


def _phase3_migration_009_promotion_eligibility_trigger(conn: sqlite3.Connection) -> None:
    """Phase 1: Add eligibility_report_id to promotion_candidates and fail-closed trigger."""
    # Add column if not present (promotion_candidates already exists from migration 004)
    try:
        conn.execute("ALTER TABLE promotion_candidates ADD COLUMN eligibility_report_id TEXT")
    except sqlite3.OperationalError:
        pass
    # Trigger: reject UPDATE/INSERT to candidate|accepted without a linked passing eligibility report
    conn.execute("DROP TRIGGER IF EXISTS promotion_candidates_require_eligibility")
    conn.execute(
        """
        CREATE TRIGGER promotion_candidates_require_eligibility
        BEFORE UPDATE OF status ON promotion_candidates
        FOR EACH ROW
        WHEN NEW.status IN ('candidate','accepted')
        BEGIN
            SELECT RAISE(ABORT, 'eligibility_report_id required for candidate/accepted; use promote_to_candidate/promote_to_accepted')
            WHERE NEW.eligibility_report_id IS NULL
               OR (SELECT passed FROM eligibility_reports WHERE eligibility_report_id = NEW.eligibility_report_id) IS NOT 1
               OR (SELECT level FROM eligibility_reports WHERE eligibility_report_id = NEW.eligibility_report_id) != NEW.status;
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER promotion_candidates_require_eligibility_insert
        BEFORE INSERT ON promotion_candidates
        FOR EACH ROW
        WHEN NEW.status IN ('candidate','accepted')
        BEGIN
            SELECT RAISE(ABORT, 'eligibility_report_id required for candidate/accepted; use promote_to_candidate/promote_to_accepted')
            WHERE NEW.eligibility_report_id IS NULL
               OR (SELECT passed FROM eligibility_reports WHERE eligibility_report_id = NEW.eligibility_report_id) IS NOT 1
               OR (SELECT level FROM eligibility_reports WHERE eligibility_report_id = NEW.eligibility_report_id) != NEW.status;
        END
        """
    )
    conn.commit()


def _phase3_migration_010_eligibility_reports_immutability(conn: sqlite3.Connection) -> None:
    """Phase 1: Prevent delete/update of eligibility_reports rows referenced by candidate/accepted (audit integrity)."""
    conn.execute("DROP TRIGGER IF EXISTS eligibility_reports_prevent_delete_when_referenced")
    conn.execute(
        """
        CREATE TRIGGER eligibility_reports_prevent_delete_when_referenced
        BEFORE DELETE ON eligibility_reports
        FOR EACH ROW
        WHEN (SELECT COUNT(*) FROM promotion_candidates
              WHERE eligibility_report_id = OLD.eligibility_report_id
                AND status IN ('candidate','accepted')) > 0
        BEGIN
            SELECT RAISE(ABORT, 'cannot delete eligibility report referenced by candidate/accepted; evidence is immutable');
        END
        """
    )
    conn.execute("DROP TRIGGER IF EXISTS eligibility_reports_prevent_update_when_referenced")
    conn.execute(
        """
        CREATE TRIGGER eligibility_reports_prevent_update_when_referenced
        BEFORE UPDATE ON eligibility_reports
        FOR EACH ROW
        WHEN (OLD.passed IS NOT NEW.passed OR OLD.level IS NOT NEW.level)
         AND (SELECT COUNT(*) FROM promotion_candidates
              WHERE eligibility_report_id = OLD.eligibility_report_id
                AND status IN ('candidate','accepted')) > 0
        BEGIN
            SELECT RAISE(ABORT, 'cannot update passed/level of eligibility report referenced by candidate/accepted; evidence is immutable');
        END
        """
    )
    conn.commit()


def _phase3_migration_011_governance_events(conn: sqlite3.Connection) -> None:
    """Phase 3 A3: Append-only governance event log (evaluate, promote, reject)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS governance_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            candidate_id TEXT,
            eligibility_report_id TEXT,
            run_key TEXT,
            dataset_id_v2 TEXT,
            artifact_refs_json TEXT
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_governance_events_candidate ON governance_events(candidate_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_governance_events_timestamp ON governance_events(timestamp);")
    conn.commit()
    conn.execute("DROP TRIGGER IF EXISTS governance_events_prevent_update")
    conn.execute(
        """
        CREATE TRIGGER governance_events_prevent_update
        BEFORE UPDATE ON governance_events
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'governance_events is append-only; updates not allowed');
        END
        """
    )
    conn.execute("DROP TRIGGER IF EXISTS governance_events_prevent_delete")
    conn.execute(
        """
        CREATE TRIGGER governance_events_prevent_delete
        BEFORE DELETE ON governance_events
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'governance_events is append-only; deletes not allowed');
        END
        """
    )
    conn.commit()


def _phase3_migration_012_artifact_lineage(conn: sqlite3.Connection) -> None:
    """Phase 3 A4: Immutable artifact lineage (which inputs/configs/engine produced this artifact hash)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS artifact_lineage (
            artifact_id TEXT PRIMARY KEY,
            run_instance_id TEXT,
            run_key TEXT,
            dataset_id_v2 TEXT,
            artifact_type TEXT NOT NULL,
            relative_path TEXT,
            sha256 TEXT NOT NULL,
            created_utc TEXT NOT NULL,
            engine_version TEXT,
            config_version TEXT,
            schema_versions_json TEXT,
            plugin_manifest_json TEXT
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_artifact_lineage_run_key ON artifact_lineage(run_key);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_artifact_lineage_dataset ON artifact_lineage(dataset_id_v2);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_artifact_lineage_created ON artifact_lineage(created_utc);")
    conn.commit()
    conn.execute("DROP TRIGGER IF EXISTS artifact_lineage_prevent_update_delete")
    conn.execute(
        """
        CREATE TRIGGER artifact_lineage_prevent_update
        BEFORE UPDATE ON artifact_lineage
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'artifact_lineage is append-only; updates not allowed');
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER artifact_lineage_prevent_delete
        BEFORE DELETE ON artifact_lineage
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'artifact_lineage is append-only; deletes not allowed');
        END
        """
    )
    conn.commit()


def _phase3_migration_013_artifact_edges(conn: sqlite3.Connection) -> None:
    """Phase 3 A4: Edges between artifacts (derived_from, uses_null, uses_folds, uses_transforms, uses_config)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS artifact_edges (
            child_artifact_id TEXT NOT NULL,
            parent_artifact_id TEXT NOT NULL,
            relation TEXT NOT NULL,
            PRIMARY KEY (child_artifact_id, parent_artifact_id, relation),
            FOREIGN KEY (child_artifact_id) REFERENCES artifact_lineage(artifact_id),
            FOREIGN KEY (parent_artifact_id) REFERENCES artifact_lineage(artifact_id)
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_artifact_edges_child ON artifact_edges(child_artifact_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_artifact_edges_parent ON artifact_edges(parent_artifact_id);")
    conn.commit()
    conn.execute("DROP TRIGGER IF EXISTS artifact_edges_prevent_update_delete")
    conn.execute(
        """
        CREATE TRIGGER artifact_edges_prevent_update
        BEFORE UPDATE ON artifact_edges
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'artifact_edges is append-only; updates not allowed');
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER artifact_edges_prevent_delete
        BEFORE DELETE ON artifact_edges
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'artifact_edges is append-only; deletes not allowed');
        END
        """
    )
    conn.commit()


MIGRATIONS_PHASE3: List[Migration] = [
    (1, "2026_02_schema_migrations_phase3", _phase3_migration_001_schema_migrations_phase3),
    (2, "2026_02_regime_runs", _phase3_migration_002_regime_runs),
    (3, "2026_02_regime_states", _phase3_migration_003_regime_states),
    (4, "2026_02_promotion_candidates", _phase3_migration_004_promotion_candidates),
    (5, "2026_02_promotion_events", _phase3_migration_005_promotion_events),
    (6, "2026_02_sweep_families", _phase3_migration_006_sweep_families),
    (7, "2026_02_sweep_hypotheses", _phase3_migration_007_sweep_hypotheses),
    (8, "2026_02_eligibility_reports", _phase3_migration_008_eligibility_reports),
    (9, "2026_02_promotion_eligibility_trigger", _phase3_migration_009_promotion_eligibility_trigger),
    (10, "2026_02_eligibility_reports_immutability", _phase3_migration_010_eligibility_reports_immutability),
    (11, "2026_02_governance_events", _phase3_migration_011_governance_events),
    (12, "2026_02_artifact_lineage", _phase3_migration_012_artifact_lineage),
    (13, "2026_02_artifact_edges", _phase3_migration_013_artifact_edges),
]


def _schema_migrations_phase3_exists(conn: sqlite3.Connection) -> bool:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations_phase3'")
    return cur.fetchone() is not None


def _max_applied_version_phase3(conn: sqlite3.Connection) -> int:
    if not _schema_migrations_phase3_exists(conn):
        return 0
    cur = conn.execute("SELECT MAX(version) FROM schema_migrations_phase3")
    row = cur.fetchone()
    if row is None or row[0] is None:
        return 0
    return int(row[0])


def _record_migration_phase3(conn: sqlite3.Connection, version: int, name: str) -> None:
    conn.execute(
        "INSERT INTO schema_migrations_phase3 (version, name, applied_at_utc, git_commit) VALUES (?, ?, ?, ?)",
        (version, name, now_utc_iso(), get_git_commit()),
    )
    conn.commit()


def run_migrations_phase3(conn: sqlite3.Connection, db_path: str | Path | None = None) -> None:
    """
    Apply Phase 3 migrations (regime_runs, regime_states) in ascending order.

    Uses schema_migrations_phase3 to track applied versions. Safe to call
    idempotently. When db_path is provided and is a file, backs up before
    applying and restores on failure.

    Call only when CRYPTO_ANALYZER_ENABLE_REGIMES=1 and the caller explicitly
    opts in. Not invoked by run_migrations() or run_migrations_v2().
    """
    db_path = str(db_path) if db_path else None

    if not _schema_migrations_phase3_exists(conn):
        backup_path = None
        if db_path and Path(db_path).is_file():
            backup_path = f"{db_path}.bak.phase3.{now_utc_iso().replace(':', '-')}"
            try:
                shutil.copy2(db_path, backup_path)
            except Exception as e:
                logger.warning("Backup before first Phase 3 migration failed: %s", e)
        try:
            _phase3_migration_001_schema_migrations_phase3(conn)
            _record_migration_phase3(conn, 1, MIGRATIONS_PHASE3[0][1])
        except Exception:
            if backup_path and Path(backup_path).is_file():
                try:
                    shutil.copy2(backup_path, db_path)
                    logger.info("Restored DB from %s after Phase 3 migration failure", backup_path)
                except Exception as restore_err:
                    logger.error("Restore from backup failed: %s", restore_err)
            raise

    max_ver = _max_applied_version_phase3(conn)

    for version, name, apply_fn in MIGRATIONS_PHASE3:
        if version <= max_ver:
            continue
        backup_path = None
        if db_path and Path(db_path).is_file():
            backup_path = f"{db_path}.bak.phase3.{now_utc_iso().replace(':', '-')}"
            try:
                shutil.copy2(db_path, backup_path)
            except Exception as e:
                logger.warning("Backup before Phase 3 migration %s failed: %s", version, e)
        try:
            apply_fn(conn)
            _record_migration_phase3(conn, version, name)
            logger.debug("Applied Phase 3 migration %s: %s", version, name)
        except Exception:
            conn.rollback()
            if backup_path and Path(backup_path).is_file():
                try:
                    shutil.copy2(backup_path, db_path)
                    logger.info(
                        "Restored DB from %s after Phase 3 migration %s failure",
                        backup_path,
                        version,
                    )
                except Exception as restore_err:
                    logger.error("Restore from backup failed: %s", restore_err)
            raise
