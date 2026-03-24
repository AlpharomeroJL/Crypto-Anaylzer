"""Tests for venue majors research universe and migrations."""

from __future__ import annotations

import sqlite3

from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.research_universe import get_benchmark_majors_assets


def test_get_benchmark_majors_assets_pivots_log_returns(tmp_path) -> None:
    db = tmp_path / "t.sqlite"
    with sqlite3.connect(str(db)) as conn:
        run_migrations(conn, str(db))
        conn.execute(
            """
            INSERT INTO venue_bars_1h (
                ts_utc, venue, product_id, open, high, low, close, volume,
                log_return, source, ingested_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2025-01-01T00:00:00+00:00",
                "coinbase_advanced",
                "BTC-USD",
                100.0,
                101.0,
                99.0,
                100.0,
                1.0,
                None,
                "test",
                "2025-01-01T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO venue_bars_1h (
                ts_utc, venue, product_id, open, high, low, close, volume,
                log_return, source, ingested_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2025-01-01T01:00:00+00:00",
                "coinbase_advanced",
                "BTC-USD",
                100.0,
                102.0,
                99.5,
                101.0,
                2.0,
                None,
                "test",
                "2025-01-01T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO venue_bars_1h (
                ts_utc, venue, product_id, open, high, low, close, volume,
                log_return, source, ingested_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2025-01-01T02:00:00+00:00",
                "coinbase_advanced",
                "BTC-USD",
                101.0,
                103.0,
                100.0,
                102.5,
                1.0,
                None,
                "test",
                "2025-01-01T00:00:00+00:00",
            ),
        )
        conn.commit()

    r, meta = get_benchmark_majors_assets(
        str(db),
        min_bars_override=2,
        venue="coinbase_advanced",
        product_ids=["BTC-USD"],
    )
    assert not r.empty
    assert "BTC-USD" in r.columns
    assert meta["asset_type"].iloc[0] == "venue_majors"
    assert len(r) >= 2


def test_migrations_create_venue_tables(tmp_path) -> None:
    db = tmp_path / "m.sqlite"
    with sqlite3.connect(str(db)) as conn:
        run_migrations(conn, str(db))
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('venue_products','venue_bars_1h')"
        )
        names = {row[0] for row in cur.fetchall()}
    assert names == {"venue_products", "venue_bars_1h"}
