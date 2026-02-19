"""
Pluggable experiment store: SQLite (default) or Postgres backend.
Research-only; no execution.
"""

from __future__ import annotations

import abc
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from crypto_analyzer.experiments import (
    load_distinct_metric_names,
    load_experiment_metrics,
    load_experiments_filtered,
    load_metric_history,
    record_experiment_run,
)


def _default_sqlite_path() -> str:
    return os.environ.get("EXPERIMENT_DB_PATH", str(Path("reports") / "experiments.db"))


class ExperimentStore(abc.ABC):
    """Abstract interface for experiment persistence."""

    @abc.abstractmethod
    def record_run(
        self,
        experiment_row: Dict[str, Any],
        metrics_dict: Optional[Dict[str, float]] = None,
        artifacts_list: Optional[List[Dict[str, str]]] = None,
    ) -> str: ...

    @abc.abstractmethod
    def load_runs(
        self,
        limit: int = 200,
        tag: Optional[str] = None,
        search: Optional[str] = None,
    ) -> pd.DataFrame: ...

    @abc.abstractmethod
    def load_metrics(self, run_id: str) -> pd.DataFrame: ...

    @abc.abstractmethod
    def load_metric_history(self, name: str, limit: int = 500) -> pd.DataFrame: ...

    @abc.abstractmethod
    def load_distinct_metric_names(self) -> list[str]: ...


class SQLiteExperimentStore(ExperimentStore):
    """Delegates to the existing SQLite-backed functions in experiments.py."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or _default_sqlite_path()

    def record_run(
        self,
        experiment_row: Dict[str, Any],
        metrics_dict: Optional[Dict[str, float]] = None,
        artifacts_list: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        return record_experiment_run(self.db_path, experiment_row, metrics_dict, artifacts_list)

    def load_runs(
        self,
        limit: int = 200,
        tag: Optional[str] = None,
        search: Optional[str] = None,
    ) -> pd.DataFrame:
        return load_experiments_filtered(self.db_path, tag=tag, search=search, limit=limit)

    def load_metrics(self, run_id: str) -> pd.DataFrame:
        return load_experiment_metrics(self.db_path, run_id)

    def load_metric_history(self, name: str, limit: int = 500) -> pd.DataFrame:
        return load_metric_history(self.db_path, name, limit=limit)

    def load_distinct_metric_names(self) -> list[str]:
        return load_distinct_metric_names(self.db_path)


class PostgresExperimentStore(ExperimentStore):
    """Postgres backend using SQLAlchemy (preferred) or psycopg2."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._engine = self._connect(dsn)

    @staticmethod
    def _connect(dsn: str):
        try:
            import sqlalchemy

            engine = sqlalchemy.create_engine(dsn)
            with engine.connect() as conn:
                conn.execute(sqlalchemy.text("SELECT 1"))
            return engine
        except Exception:
            pass

        try:
            import psycopg2

            conn = psycopg2.connect(dsn)
            conn.close()
            return dsn
        except Exception as exc:
            print(
                f"[experiment_store] Postgres connection failed: {exc}\n"
                "  Set EXPERIMENT_DB_DSN to a valid Postgres DSN or unset it "
                "to use the SQLite fallback."
            )
            raise

    def _read_sql(self, query: str, params=None) -> pd.DataFrame:
        import sqlalchemy

        if isinstance(self._engine, str):
            import psycopg2

            conn = psycopg2.connect(self._engine)
            try:
                return pd.read_sql_query(query, conn, params=params)
            finally:
                conn.close()
        with self._engine.connect() as conn:
            return pd.read_sql_query(sqlalchemy.text(query), conn, params=params or {})

    def record_run(
        self,
        experiment_row: Dict[str, Any],
        metrics_dict: Optional[Dict[str, float]] = None,
        artifacts_list: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        raise NotImplementedError("Postgres write support not yet implemented")

    def load_runs(
        self,
        limit: int = 200,
        tag: Optional[str] = None,
        search: Optional[str] = None,
    ) -> pd.DataFrame:
        raise NotImplementedError("Postgres read support not yet implemented")

    def load_metrics(self, run_id: str) -> pd.DataFrame:
        raise NotImplementedError("Postgres read support not yet implemented")

    def load_metric_history(self, name: str, limit: int = 500) -> pd.DataFrame:
        raise NotImplementedError("Postgres read support not yet implemented")

    def load_distinct_metric_names(self) -> list[str]:
        raise NotImplementedError("Postgres read support not yet implemented")


def get_experiment_store() -> ExperimentStore:
    """Factory: Postgres if EXPERIMENT_DB_DSN is set, else SQLite."""
    dsn = os.environ.get("EXPERIMENT_DB_DSN")
    if dsn:
        try:
            return PostgresExperimentStore(dsn)
        except Exception:
            print("[experiment_store] Falling back to SQLite after Postgres failure.")
    return SQLiteExperimentStore()
