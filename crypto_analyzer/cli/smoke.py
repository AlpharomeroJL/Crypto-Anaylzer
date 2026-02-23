"""
CI smoke: synthetic-data, no-network check. Exercises migrations, dataset_id_v2, run identity.
Use: crypto-analyzer smoke --ci
"""

from __future__ import annotations

import os
import socket as _socket_module
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from typing import List, Optional

_NETWORK_DISABLED_MSG = "Network access disabled for CI smoke (--ci / CRYPTO_ANALYZER_NO_NETWORK)."


@contextmanager
def network_guard():
    """Monkeypatch socket to block network/DNS; raises RuntimeError if code tries to open connections."""
    orig_socket = _socket_module.socket
    orig_create_connection = getattr(_socket_module, "create_connection", None)
    orig_socketpair = getattr(_socket_module, "socketpair", None)
    orig_getaddrinfo = getattr(_socket_module, "getaddrinfo", None)

    def _block(*args, **kwargs):
        raise RuntimeError(_NETWORK_DISABLED_MSG)

    try:
        _socket_module.socket = _block
        if orig_create_connection is not None:
            _socket_module.create_connection = _block
        if orig_socketpair is not None:
            _socket_module.socketpair = _block
        if orig_getaddrinfo is not None:
            _socket_module.getaddrinfo = _block
        yield
    finally:
        _socket_module.socket = orig_socket
        if orig_create_connection is not None:
            _socket_module.create_connection = orig_create_connection
        if orig_socketpair is not None:
            _socket_module.socketpair = orig_socketpair
        if orig_getaddrinfo is not None:
            _socket_module.getaddrinfo = orig_getaddrinfo


def _ci_smoke() -> int:
    """Temp DB, migrations, minimal synthetic data, dataset_id_v2 (STRICT), run identity. No network."""
    from crypto_analyzer.core.run_identity import build_run_identity, compute_run_key
    from crypto_analyzer.dataset_v2 import get_dataset_id_v2
    from crypto_analyzer.db.migrations import run_migrations
    from crypto_analyzer.db.migrations_phase3 import run_migrations_phase3

    fd, path = tempfile.mkstemp(suffix=".sqlite")
    try:
        os.close(fd)
        with sqlite3.connect(path) as conn:
            run_migrations(conn, path)
            run_migrations_phase3(conn, path)
            conn.execute(
                "INSERT INTO spot_price_snapshots (ts_utc, symbol, spot_price_usd, spot_source) VALUES (?, ?, ?, ?)",
                ("2020-01-01T00:00:00", "BTC", 50000.0, "ci"),
            )
            conn.commit()
        dataset_id_v2, meta = get_dataset_id_v2(path, mode="STRICT")
        payload = {"dataset_id_v2": dataset_id_v2, "freq": "1h"}
        run_key = compute_run_key(payload)
        identity = build_run_identity(payload, "ci-smoke-1")
        print("CI smoke OK: migrations, dataset_id_v2 (STRICT), run_key, run_instance_id")
        print(f"  dataset_id_v2={dataset_id_v2}  run_key={run_key}  run_instance_id={identity.run_instance_id}")
        return 0
    except Exception as e:
        print(f"CI smoke failed: {e}", file=sys.stderr)
        return 1
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if "--ci" not in argv:
        print("Usage: crypto-analyzer smoke --ci")
        print("  Runs synthetic-data, no-network smoke (migrations, dataset_id_v2, run identity).")
        return 0
    use_guard = ("--ci" in argv) or (os.environ.get("CRYPTO_ANALYZER_NO_NETWORK") == "1")
    if use_guard:
        with network_guard():
            return _ci_smoke()
    return _ci_smoke()
