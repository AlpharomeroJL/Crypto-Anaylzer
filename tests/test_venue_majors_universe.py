"""Tests for venue majors research universe and migrations."""

from __future__ import annotations

import sqlite3

from crypto_analyzer.cli.venue_sync import _flush_closed_hourly_bars, _update_bucket
from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.providers.coinbase_advanced.ws_client import TradeTick
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


def test_ws_hourly_bucket_flush_writes_venue_bars(tmp_path) -> None:
    db = tmp_path / "ws.sqlite"
    with sqlite3.connect(str(db)) as conn:
        run_migrations(conn, str(db))
        buckets = {}
        _update_bucket(
            buckets,
            TradeTick(product_id="BTC-USD", event_ts=1735689605, price=100.0, size=1.0),  # 2025-01-01 00:00:05Z
        )
        _update_bucket(
            buckets,
            TradeTick(product_id="BTC-USD", event_ts=1735691405, price=101.0, size=2.0),  # 2025-01-01 00:30:05Z
        )
        _update_bucket(
            buckets,
            TradeTick(product_id="BTC-USD", event_ts=1735693205, price=99.0, size=1.5),  # 2025-01-01 01:00:05Z
        )

        n = _flush_closed_hourly_bars(
            conn,
            venue="coinbase_advanced",
            source="coinbase_advanced_ws_market_trades",
            now_unix=1735696800,  # 2025-01-01 02:00:00Z
            buckets=buckets,
        )
        assert n >= 1
        row = conn.execute(
            """
            SELECT ts_utc, open, high, low, close, volume, source
            FROM venue_bars_1h
            WHERE venue = ? AND product_id = ?
            ORDER BY ts_utc ASC
            LIMIT 1
            """,
            ("coinbase_advanced", "BTC-USD"),
        ).fetchone()
        assert row is not None
        assert row[1] == 100.0
        assert row[2] == 101.0
        assert row[3] == 100.0
        assert row[4] == 101.0
        assert row[5] == 3.0
        assert str(row[6]).startswith("coinbase_advanced_ws_")
