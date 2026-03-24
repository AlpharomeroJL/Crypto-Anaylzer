"""reportv2-style dataset hash scoping: DEX runs ignore venue table content."""

from __future__ import annotations

import sqlite3

from crypto_analyzer.dataset import dataset_fingerprint_tables, get_dataset_id
from crypto_analyzer.dataset_v2 import DATASET_HASH_SCOPE_V2_DEX, DATASET_HASH_SCOPE_V2_MAJORS, get_dataset_id_v2


def test_dataset_fingerprint_tables_majors_only_venue(tmp_path) -> None:
    assert dataset_fingerprint_tables("majors") == ["venue_bars_1h", "venue_products"]
    dex = dataset_fingerprint_tables("dex")
    assert "venue_bars_1h" not in dex
    assert "venue_products" not in dex
    assert "sol_monitor_snapshots" in dex


def test_v2_dex_id_ignores_venue_content(tmp_path) -> None:
    db = str(tmp_path / "scope.sqlite")
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE spot_price_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_utc TEXT NOT NULL,
                symbol TEXT NOT NULL,
                spot_price_usd REAL NOT NULL,
                spot_source TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO spot_price_snapshots (ts_utc, symbol, spot_price_usd, spot_source) VALUES (?, ?, ?, ?)",
            ("2026-01-01T00:00:00", "BTC", 1.0, "t"),
        )
        conn.commit()
    id_dex_before, _ = get_dataset_id_v2(db, mode="STRICT", scope=list(DATASET_HASH_SCOPE_V2_DEX))

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE venue_bars_1h (
                ts_utc TEXT NOT NULL, venue TEXT NOT NULL, product_id TEXT NOT NULL,
                open REAL, high REAL, low REAL, close REAL NOT NULL, volume REAL,
                log_return REAL, source TEXT, ingested_at_utc TEXT NOT NULL,
                PRIMARY KEY (ts_utc, venue, product_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO venue_bars_1h VALUES (
                '2026-01-01T00:00:00+00:00', 'coinbase_advanced', 'BTC-USD',
                1, 1, 1, 1, 1, 0, 'x', '2026-01-01T00:00:00+00:00'
            )
            """
        )
        conn.commit()

    id_dex_after, _ = get_dataset_id_v2(db, mode="STRICT", scope=list(DATASET_HASH_SCOPE_V2_DEX))
    assert id_dex_before == id_dex_after

    id_majors, meta = get_dataset_id_v2(db, mode="STRICT", scope=list(DATASET_HASH_SCOPE_V2_MAJORS))
    assert id_majors != id_dex_before
    assert set(meta.get("dataset_hash_scope", [])) == set(DATASET_HASH_SCOPE_V2_MAJORS)


def test_v1_get_dataset_id_still_full_known_tables(tmp_path) -> None:
    """get_dataset_id() remains full KNOWN_TABLES for backward compatibility."""
    db = str(tmp_path / "v1.sqlite")
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE sol_monitor_snapshots (ts_utc TEXT, dex_price_usd REAL)")
        conn.execute("INSERT INTO sol_monitor_snapshots VALUES ('2026-01-01', 1.0)")
        conn.commit()
    _ = get_dataset_id(db)
    # No exception; fingerprint includes whatever tables exist among KNOWN_TABLES
