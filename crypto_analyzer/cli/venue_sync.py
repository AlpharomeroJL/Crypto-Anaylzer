#!/usr/bin/env python3
"""
Backfill Coinbase Advanced Trade public market data into venue_* tables.

Phase 1: public market data only (REST + optional websocket live path). No auth.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from crypto_analyzer.config import (
    db_path as config_db_path,
)
from crypto_analyzer.config import (
    resolve_config_db_path,
    venue_coinbase_advanced_product_ids,
    venue_coinbase_advanced_rest_base,
    venue_coinbase_advanced_slug,
)
from crypto_analyzer.db.migrations import run_migrations
from crypto_analyzer.providers.coinbase_advanced.rest_client import CoinbaseAdvancedRestClient
from crypto_analyzer.providers.coinbase_advanced.ws_client import CoinbaseAdvancedWsClient, TradeTick


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_iso_to_ts(s: str) -> int:
    """Parse ISO UTC string to unix seconds."""
    t = s.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    dt = datetime.fromisoformat(t)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _bar_ts_iso(start_unix: int) -> str:
    return datetime.fromtimestamp(start_unix, tz=timezone.utc).isoformat(timespec="seconds")


def recompute_log_returns_for_product(conn: sqlite3.Connection, venue: str, product_id: str) -> None:
    """Set log_return = log(close/prev_close) per product (first bar NULL)."""
    cur = conn.execute(
        """
        SELECT ts_utc, close FROM venue_bars_1h
        WHERE venue = ? AND product_id = ?
        ORDER BY ts_utc ASC
        """,
        (venue, product_id),
    )
    rows = cur.fetchall()
    prev_close: Optional[float] = None
    for ts_utc, close in rows:
        lr: Optional[float] = None
        c = float(close) if close is not None else None
        if prev_close is not None and prev_close > 0 and c is not None and c > 0:
            lr = math.log(c / prev_close)
        conn.execute(
            """
            UPDATE venue_bars_1h SET log_return = ?
            WHERE ts_utc = ? AND venue = ? AND product_id = ?
            """,
            (lr, ts_utc, venue, product_id),
        )
        prev_close = c


def upsert_product_row(
    conn: sqlite3.Connection,
    venue: str,
    product: Dict[str, Any],
    *,
    now_iso: str,
) -> None:
    pid = str(product.get("product_id") or "").strip()
    if not pid:
        return
    raw = json.dumps(product, sort_keys=True)
    conn.execute(
        """
        INSERT INTO venue_products (
            venue, product_id, base_currency_id, quote_currency_id, status,
            quote_increment, base_increment, display_name, raw_json,
            fetched_at_utc, updated_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(venue, product_id) DO UPDATE SET
            base_currency_id = excluded.base_currency_id,
            quote_currency_id = excluded.quote_currency_id,
            status = excluded.status,
            quote_increment = excluded.quote_increment,
            base_increment = excluded.base_increment,
            display_name = excluded.display_name,
            raw_json = excluded.raw_json,
            updated_at_utc = excluded.updated_at_utc
        """,
        (
            venue,
            pid,
            product.get("base_currency_id"),
            product.get("quote_currency_id"),
            product.get("status"),
            str(product.get("quote_increment")) if product.get("quote_increment") is not None else None,
            str(product.get("base_increment")) if product.get("base_increment") is not None else None,
            product.get("display_name") or pid,
            raw,
            now_iso,
            now_iso,
        ),
    )


def upsert_candle_rows(
    conn: sqlite3.Connection,
    venue: str,
    product_id: str,
    candles: Sequence[Any],
    *,
    source: str,
    ingested_iso: str,
) -> int:
    n = 0
    for c in candles:
        ts_utc = _bar_ts_iso(c.start_unix)
        conn.execute(
            """
            INSERT INTO venue_bars_1h (
                ts_utc, venue, product_id, open, high, low, close, volume,
                log_return, source, ingested_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
            ON CONFLICT(ts_utc, venue, product_id) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                volume = excluded.volume,
                source = excluded.source,
                ingested_at_utc = excluded.ingested_at_utc
            """,
            (
                ts_utc,
                venue,
                product_id,
                c.open,
                c.high,
                c.low,
                c.close,
                c.volume,
                source,
                ingested_iso,
            ),
        )
        n += 1
    return n


def _hour_open_unix(ts_unix: int) -> int:
    return int(ts_unix - (ts_unix % 3600))


def _make_candle_row_from_ohlcv(hour_open_unix: int, ohlcv: Dict[str, float]) -> Any:
    class _Candle:
        def __init__(self, start_unix: int, open_: float, high: float, low: float, close: float, volume: float) -> None:
            self.start_unix = start_unix
            self.open = open_
            self.high = high
            self.low = low
            self.close = close
            self.volume = volume

    return _Candle(
        hour_open_unix,
        float(ohlcv["open"]),
        float(ohlcv["high"]),
        float(ohlcv["low"]),
        float(ohlcv["close"]),
        float(ohlcv["volume"]),
    )


def _update_bucket(buckets: Dict[tuple[str, int], Dict[str, float]], tick: TradeTick) -> None:
    hour_open = _hour_open_unix(int(tick.event_ts))
    key = (tick.product_id, hour_open)
    rec = buckets.get(key)
    if rec is None:
        buckets[key] = {
            "open": tick.price,
            "high": tick.price,
            "low": tick.price,
            "close": tick.price,
            "volume": max(0.0, tick.size),
        }
        return
    rec["high"] = max(float(rec["high"]), tick.price)
    rec["low"] = min(float(rec["low"]), tick.price)
    rec["close"] = tick.price
    rec["volume"] = float(rec["volume"]) + max(0.0, tick.size)


def _flush_closed_hourly_bars(
    conn: sqlite3.Connection,
    *,
    venue: str,
    source: str,
    now_unix: int,
    buckets: Dict[tuple[str, int], Dict[str, float]],
) -> int:
    now_iso = _utc_now_iso()
    current_hour = _hour_open_unix(now_unix)
    by_product: Dict[str, List[Any]] = {}
    done_keys: List[tuple[str, int]] = []
    for (product_id, hour_open), ohlcv in buckets.items():
        if hour_open >= current_hour:
            continue
        by_product.setdefault(product_id, []).append(_make_candle_row_from_ohlcv(hour_open, ohlcv))
        done_keys.append((product_id, hour_open))
    n_rows = 0
    for product_id, rows in by_product.items():
        rows.sort(key=lambda c: c.start_unix)
        n_rows += upsert_candle_rows(conn, venue, product_id, rows, source=source, ingested_iso=now_iso)
        recompute_log_returns_for_product(conn, venue, product_id)
    for key in done_keys:
        buckets.pop(key, None)
    if n_rows:
        conn.commit()
    return n_rows


def cmd_ws_live(
    db_path: str,
    *,
    venue: str,
    product_ids: List[str],
    ws_base: str,
    channel: str,
    run_seconds: int,
    status_interval_sec: int,
    max_reconnects: int,
) -> int:
    source = f"coinbase_advanced_ws_{channel}"
    start_wall = time.time()
    buckets: Dict[tuple[str, int], Dict[str, float]] = {}
    reconnects = 0
    total_flushed = 0
    print(
        f"Starting Coinbase WS live ingest (channel={channel}, products={len(product_ids)}, run_seconds={run_seconds})",
        flush=True,
    )
    with sqlite3.connect(db_path) as conn:
        run_migrations(conn, db_path)
        while True:
            now_wall = time.time()
            if (now_wall - start_wall) >= float(run_seconds):
                break
            ws = CoinbaseAdvancedWsClient(ws_url=ws_base, product_ids=product_ids, channel=channel)
            try:
                ws.connect()
                print(f"WS connected: {ws_base}", flush=True)
                next_status = now_wall + float(status_interval_sec)
                for tick in ws.iter_ticks():
                    _update_bucket(buckets, tick)
                    flushed = _flush_closed_hourly_bars(
                        conn,
                        venue=venue,
                        source=source,
                        now_unix=int(time.time()),
                        buckets=buckets,
                    )
                    total_flushed += flushed
                    now_wall = time.time()
                    if now_wall >= next_status:
                        hs = ws.health.snapshot(now_wall)
                        print(
                            "WS health: "
                            f"messages={int(hs['messages'])} ticks={int(hs['ticks'])} reconnects={reconnects} "
                            f"last_msg_age_s={hs['last_msg_age_s']:.1f} feed_lag_s={hs['feed_lag_s']:.1f} "
                            f"bars_flushed={total_flushed}",
                            flush=True,
                        )
                        next_status = now_wall + float(status_interval_sec)
                    if (now_wall - start_wall) >= float(run_seconds):
                        break
            except KeyboardInterrupt:
                print("Interrupted by user.", flush=True)
                break
            except Exception as e:
                reconnects += 1
                print(f"WS reconnect: #{reconnects} reason={e}", file=sys.stderr, flush=True)
                if reconnects > max_reconnects:
                    print("Error: max reconnect limit reached.", file=sys.stderr)
                    return 1
                time.sleep(2.0)
            finally:
                ws.close()
    print(f"WS live ingest complete. bars_flushed={total_flushed} source={source}")
    return 0


def cmd_products(
    db_path: str,
    *,
    rest_base: str,
    venue: str,
    product_ids: List[str],
    strict: bool,
) -> int:
    client = CoinbaseAdvancedRestClient(base_url=rest_base)
    now = _utc_now_iso()
    data = client.list_public_products(product_ids=product_ids)
    products = data.get("products") or []
    found = {str(p.get("product_id")) for p in products if p.get("product_id")}
    if strict:
        for pid in product_ids:
            if pid not in found:
                print(f"Error: product_id {pid!r} not returned by API.", file=sys.stderr)
                return 1
    allow = set(product_ids)
    n_up = 0
    with sqlite3.connect(db_path) as conn:
        run_migrations(conn, db_path)
        for p in products:
            pid = str(p.get("product_id") or "").strip()
            if pid not in allow:
                continue
            upsert_product_row(conn, venue, p, now_iso=now)
            n_up += 1
        conn.commit()
    print(f"venue_products upserted: {n_up} row(s).")
    return 0


def cmd_candles(
    db_path: str,
    *,
    rest_base: str,
    venue: str,
    product_ids: List[str],
    start_sec: int,
    end_sec: int,
) -> int:
    client = CoinbaseAdvancedRestClient(base_url=rest_base)
    now = _utc_now_iso()
    source = "coinbase_advanced_rest"
    total = 0
    with sqlite3.connect(db_path) as conn:
        run_migrations(conn, db_path)
        for pid in product_ids:
            candles = client.iter_public_candles_1h(
                pid,
                start_sec=start_sec,
                end_sec=end_sec,
            )
            n = upsert_candle_rows(conn, venue, pid, candles, source=source, ingested_iso=now)
            recompute_log_returns_for_product(conn, venue, pid)
            total += n
            print(f"  {pid}: {n} candle row(s)")
        conn.commit()
    print(f"venue_bars_1h total rows written/updated: {total}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    ap = argparse.ArgumentParser(description="Sync Coinbase Advanced Trade public data into venue_* tables")
    ap.add_argument("--db", default=None, help="SQLite path (default: config db.path)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_prod = sub.add_parser("products", help="Fetch product metadata into venue_products")
    p_prod.add_argument(
        "--strict",
        action="store_true",
        help="Exit with error if a configured product_id is missing from the API response",
    )

    p_candles = sub.add_parser("candles", help="Backfill 1h candles into venue_bars_1h")
    p_candles.add_argument(
        "--start",
        default=None,
        help="Interval start (ISO UTC), e.g. 2025-01-01T00:00:00Z. Default: 30 days ago.",
    )
    p_candles.add_argument(
        "--end",
        default=None,
        help="Interval end (ISO UTC). Default: now.",
    )

    p_all = sub.add_parser("all", help="Run products then candles")
    p_all.add_argument("--strict", action="store_true", help="Same as products --strict")
    p_all.add_argument("--start", default=None, help="candles --start")
    p_all.add_argument("--end", default=None, help="candles --end")

    p_ws = sub.add_parser("ws-live", help="Run public websocket live majors ingest into venue_bars_1h")
    p_ws.add_argument(
        "--run-seconds",
        type=int,
        default=120,
        help="How long to run websocket live ingestion before exiting (default: 120).",
    )
    p_ws.add_argument(
        "--status-interval-sec",
        type=int,
        default=15,
        help="Print WS health/lag status every N seconds (default: 15).",
    )
    p_ws.add_argument(
        "--max-reconnects",
        type=int,
        default=10,
        help="Maximum reconnect attempts before failing (default: 10).",
    )
    p_ws.add_argument(
        "--channel",
        choices=["market_trades", "ticker"],
        default="market_trades",
        help="Public websocket channel to consume (default: market_trades).",
    )
    p_ws.add_argument(
        "--ws-base",
        default="wss://advanced-trade-ws.coinbase.com",
        help="Coinbase websocket base URL.",
    )

    args = ap.parse_args(argv)
    raw_db = args.db or config_db_path()
    db_path = resolve_config_db_path(str(raw_db))

    rest_base = venue_coinbase_advanced_rest_base()
    venue = venue_coinbase_advanced_slug()
    product_ids = venue_coinbase_advanced_product_ids()
    if not product_ids:
        print("Error: config venue.coinbase_advanced.product_ids is empty.", file=sys.stderr)
        return 1

    end_default = datetime.now(timezone.utc)
    start_default = end_default - timedelta(days=30)

    if args.cmd == "products":
        return cmd_products(db_path, rest_base=rest_base, venue=venue, product_ids=product_ids, strict=args.strict)

    if args.cmd == "candles":
        end_sec = _parse_iso_to_ts(args.end) if args.end else int(end_default.timestamp())
        start_sec = _parse_iso_to_ts(args.start) if args.start else int(start_default.timestamp())
        if end_sec <= start_sec:
            print("Error: --end must be after --start.", file=sys.stderr)
            return 1
        return cmd_candles(
            db_path,
            rest_base=rest_base,
            venue=venue,
            product_ids=product_ids,
            start_sec=start_sec,
            end_sec=end_sec,
        )

    if args.cmd == "all":
        r = cmd_products(db_path, rest_base=rest_base, venue=venue, product_ids=product_ids, strict=args.strict)
        if r != 0:
            return r
        end_sec = _parse_iso_to_ts(args.end) if args.end else int(end_default.timestamp())
        start_sec = _parse_iso_to_ts(args.start) if args.start else int(start_default.timestamp())
        if end_sec <= start_sec:
            print("Error: --end must be after --start.", file=sys.stderr)
            return 1
        return cmd_candles(
            db_path,
            rest_base=rest_base,
            venue=venue,
            product_ids=product_ids,
            start_sec=start_sec,
            end_sec=end_sec,
        )

    if args.cmd == "ws-live":
        return cmd_ws_live(
            db_path,
            venue=venue,
            product_ids=product_ids,
            ws_base=str(args.ws_base),
            channel=str(args.channel),
            run_seconds=max(1, int(args.run_seconds)),
            status_interval_sec=max(5, int(args.status_interval_sec)),
            max_reconnects=max(0, int(args.max_reconnects)),
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
