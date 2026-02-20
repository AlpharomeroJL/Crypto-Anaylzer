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

from ..governance import get_git_commit
from ..timeutils import now_utc_iso

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


MIGRATIONS_PHASE3: List[Migration] = [
    (1, "2026_02_schema_migrations_phase3", _phase3_migration_001_schema_migrations_phase3),
    (2, "2026_02_regime_runs", _phase3_migration_002_regime_runs),
    (3, "2026_02_regime_states", _phase3_migration_003_regime_states),
    (4, "2026_02_promotion_candidates", _phase3_migration_004_promotion_candidates),
    (5, "2026_02_promotion_events", _phase3_migration_005_promotion_events),
    (6, "2026_02_sweep_families", _phase3_migration_006_sweep_families),
    (7, "2026_02_sweep_hypotheses", _phase3_migration_007_sweep_hypotheses),
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
