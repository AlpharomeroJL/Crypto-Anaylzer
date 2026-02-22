"""
Versioned schema migrations (Phase 2). Tracks applied migrations in schema_migrations;
applies in ascending version; backs up DB file before apply and restores on failure.
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

# (version, name, apply_function)
Migration = Tuple[int, str, Callable[[sqlite3.Connection], None]]


def _migration_001_create_schema_migrations(conn: sqlite3.Connection) -> None:
    """Create schema_migrations table and record this migration."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at_utc TEXT NOT NULL,
            git_commit TEXT
        );
        """
    )
    conn.commit()


def _migration_002_factor_model_runs(conn: sqlite3.Connection) -> None:
    """Create factor_model_runs table per schema_plan."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS factor_model_runs (
            factor_run_id TEXT PRIMARY KEY,
            created_at_utc TEXT NOT NULL,
            dataset_id TEXT NOT NULL,
            freq TEXT NOT NULL,
            window_bars INTEGER NOT NULL,
            min_obs INTEGER NOT NULL,
            factors_json TEXT NOT NULL,
            estimator TEXT NOT NULL,
            params_json TEXT
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_factor_runs_dataset_freq ON factor_model_runs(dataset_id, freq);")
    conn.commit()


def _migration_003_factor_betas(conn: sqlite3.Connection) -> None:
    """Create factor_betas table per schema_plan."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS factor_betas (
            factor_run_id TEXT NOT NULL,
            ts_utc TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            factor_name TEXT NOT NULL,
            beta REAL,
            alpha REAL,
            r2 REAL,
            PRIMARY KEY (factor_run_id, ts_utc, asset_id, factor_name)
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_factor_betas_ts ON factor_betas(factor_run_id, ts_utc);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_factor_betas_asset ON factor_betas(factor_run_id, asset_id);")
    conn.commit()


def _migration_004_residual_returns(conn: sqlite3.Connection) -> None:
    """Create residual_returns table per schema_plan."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS residual_returns (
            factor_run_id TEXT NOT NULL,
            ts_utc TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            resid_log_return REAL,
            PRIMARY KEY (factor_run_id, ts_utc, asset_id)
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_resid_ts ON residual_returns(factor_run_id, ts_utc);")
    conn.commit()


MIGRATIONS: List[Migration] = [
    (1, "2026_02_schema_migrations", _migration_001_create_schema_migrations),
    (2, "2026_02_factor_model_runs", _migration_002_factor_model_runs),
    (3, "2026_02_factor_betas", _migration_003_factor_betas),
    (4, "2026_02_residual_returns", _migration_004_residual_returns),
]


def _schema_migrations_exists(conn: sqlite3.Connection) -> bool:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
    return cur.fetchone() is not None


def _max_applied_version(conn: sqlite3.Connection) -> int:
    cur = conn.execute("SELECT MAX(version) FROM schema_migrations")
    row = cur.fetchone()
    if row is None or row[0] is None:
        return 0
    return int(row[0])


def _record_migration(conn: sqlite3.Connection, version: int, name: str) -> None:
    conn.execute(
        "INSERT INTO schema_migrations (version, name, applied_at_utc, git_commit) VALUES (?, ?, ?, ?)",
        (version, name, now_utc_iso(), get_git_commit()),
    )
    conn.commit()


def run_migrations_v2(conn: sqlite3.Connection, db_path: str | Path | None = None) -> None:
    """
    Apply versioned migrations in ascending order. Uses schema_migrations to track
    applied versions. When db_path is provided, backs up the DB file before applying
    any new migration and restores from backup on failure.
    When db_path is None (e.g. in-memory or tests), no backup is made; call with
    db_path from production entrypoints (ingest, read_api) for backup/restore.
    """
    db_path = str(db_path) if db_path else None
    if db_path is None:
        logger.info(
            "run_migrations_v2 called without db_path: backup/restore disabled. "
            "Pass db_path from ingest/read_api for on-disk backup on migration."
        )

    # Bootstrap: if schema_migrations table doesn't exist, run migration 1
    if not _schema_migrations_exists(conn):
        backup_path = None
        if db_path and Path(db_path).is_file():
            backup_path = f"{db_path}.bak.{now_utc_iso().replace(':', '-')}"
            try:
                shutil.copy2(db_path, backup_path)
            except Exception as e:
                logger.warning("Backup before first migration failed: %s", e)
        try:
            _migration_001_create_schema_migrations(conn)
            _record_migration(conn, 1, MIGRATIONS[0][1])
        except Exception:
            if backup_path and Path(backup_path).is_file():
                try:
                    shutil.copy2(backup_path, db_path)
                    logger.info("Restored DB from %s after migration failure", backup_path)
                except Exception as restore_err:
                    logger.error("Restore from backup failed: %s", restore_err)
            raise

    max_ver = _max_applied_version(conn)

    for version, name, apply_fn in MIGRATIONS:
        if version <= max_ver:
            continue
        backup_path = None
        if db_path and Path(db_path).is_file():
            backup_path = f"{db_path}.bak.{now_utc_iso().replace(':', '-')}"
            try:
                shutil.copy2(db_path, backup_path)
            except Exception as e:
                logger.warning("Backup before migration %s failed: %s", version, e)
        try:
            apply_fn(conn)
            _record_migration(conn, version, name)
            logger.debug("Applied migration %s: %s", version, name)
        except Exception:
            conn.rollback()
            if backup_path and Path(backup_path).is_file():
                try:
                    shutil.copy2(backup_path, db_path)
                    logger.info("Restored DB from %s after migration %s failure", backup_path, version)
                except Exception as restore_err:
                    logger.error("Restore from backup failed: %s", restore_err)
            raise
