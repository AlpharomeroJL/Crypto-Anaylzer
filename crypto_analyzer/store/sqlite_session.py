"""
SQLite connection lifecycle: context manager with guaranteed close and foreign_keys=ON.
Phase 3.5 A3. Use for all DB access to avoid Windows file-lock issues.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Union


@contextmanager
def sqlite_conn(db_path: Union[str, Path]) -> Generator[sqlite3.Connection, None, None]:
    """
    Yield a SQLite connection that is always closed on exit.
    Enables PRAGMA foreign_keys=ON at open for referential integrity.
    """
    path = str(Path(db_path).resolve())
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()
        yield conn
    finally:
        conn.close()
