#!/usr/bin/env python3
"""
Backfill Coinbase Advanced Trade public market data into venue_* tables.

Phase 1: REST only (products + 1h candles). Does not use poll/ingest or authenticated APIs.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
