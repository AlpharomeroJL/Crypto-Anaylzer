"""
Public Coinbase Advanced websocket market-data client (majors only, no auth).

Scope:
- subscribes to market_trades or ticker
- extracts trade-like ticks (price, size, event_ts)
- aggregates to 1h OHLCV buckets (bar-open timestamp)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

try:
    from websocket import WebSocket, WebSocketConnectionClosedException, create_connection
except Exception:  # pragma: no cover - handled at runtime when ws-live is invoked
    WebSocket = object  # type: ignore[assignment]

    class WebSocketConnectionClosedException(Exception):
        pass

    create_connection = None

COINBASE_ADVANCED_WS_BASE = "wss://advanced-trade-ws.coinbase.com"
WS_CONNECT_TIMEOUT_S = 20.0
WS_READ_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class TradeTick:
    product_id: str
    event_ts: int
    price: float
    size: float


@dataclass
class WsHealth:
    messages: int = 0
    ticks: int = 0
    reconnects: int = 0
    last_msg_wall_ts: float = 0.0
    last_event_ts: int = 0

    def snapshot(self, now_wall_ts: float) -> Dict[str, float]:
        last_msg_age_s = max(0.0, now_wall_ts - self.last_msg_wall_ts) if self.last_msg_wall_ts > 0 else float("inf")
        feed_lag_s = max(0.0, now_wall_ts - float(self.last_event_ts)) if self.last_event_ts > 0 else float("inf")
        return {
            "messages": float(self.messages),
            "ticks": float(self.ticks),
            "reconnects": float(self.reconnects),
            "last_msg_age_s": last_msg_age_s,
            "feed_lag_s": feed_lag_s,
        }


def _parse_event_ts(raw: Optional[str]) -> Optional[int]:
    if not raw:
        return None
    s = str(raw).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _to_float(raw: object, default: float = 0.0) -> float:
    if raw is None:
        return default
    try:
        return float(str(raw))
    except (TypeError, ValueError):
        return default


class CoinbaseAdvancedWsClient:
    """Small public websocket client for Coinbase market data."""

    def __init__(
        self,
        *,
        ws_url: str = COINBASE_ADVANCED_WS_BASE,
        product_ids: Optional[List[str]] = None,
        channel: str = "market_trades",
        connect_timeout_s: float = WS_CONNECT_TIMEOUT_S,
        read_timeout_s: float = WS_READ_TIMEOUT_S,
    ) -> None:
        self._ws_url = ws_url.rstrip("/")
        self._product_ids = [str(x).strip() for x in (product_ids or []) if str(x).strip()]
        self._channel = str(channel).strip()
        self._connect_timeout_s = connect_timeout_s
        self._read_timeout_s = read_timeout_s
        self.health = WsHealth()
        self._ws: Optional[WebSocket] = None

    def connect(self) -> None:
        if create_connection is None:
            raise RuntimeError(
                "websocket-client is not installed. Install dependencies and retry: "
                "python -m pip install websocket-client"
            )
        self._ws = create_connection(self._ws_url, timeout=self._connect_timeout_s)
        self._ws.settimeout(self._read_timeout_s)
        subscribe = {
            "type": "subscribe",
            "channel": self._channel,
            "product_ids": self._product_ids,
        }
        self._ws.send(json.dumps(subscribe))
        self.health.reconnects += 1

    def close(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    def _recv_json(self) -> Optional[Dict[str, object]]:
        if self._ws is None:
            return None
        try:
            raw = self._ws.recv()
        except TimeoutError:
            return None
        except WebSocketConnectionClosedException:
            raise
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(msg, dict):
            self.health.messages += 1
            self.health.last_msg_wall_ts = time.time()
            return msg
        return None

    def iter_ticks(self) -> Iterable[TradeTick]:
        """Yield trade-like ticks from websocket messages."""
        while True:
            msg = self._recv_json()
            if msg is None:
                continue
            channel = str(msg.get("channel") or "")
            if channel not in ("market_trades", "ticker"):
                continue
            events = msg.get("events")
            if not isinstance(events, list):
                continue
            for ev in events:
                if not isinstance(ev, dict):
                    continue
                trades = ev.get("trades") if channel == "market_trades" else ev.get("tickers")
                if not isinstance(trades, list):
                    continue
                for tr in trades:
                    if not isinstance(tr, dict):
                        continue
                    pid = str(tr.get("product_id") or "").strip()
                    if not pid:
                        continue
                    px = _to_float(tr.get("price"))
                    if px <= 0:
                        continue
                    # market_trades has "size"; ticker may have "volume_24_h", so keep non-negative fallback
                    sz = _to_float(tr.get("size"), default=0.0)
                    if sz < 0:
                        sz = 0.0
                    evt_ts = _parse_event_ts(tr.get("time"))
                    if evt_ts is None:
                        evt_ts = int(time.time())
                    self.health.ticks += 1
                    self.health.last_event_ts = max(self.health.last_event_ts, evt_ts)
                    yield TradeTick(product_id=pid, event_ts=evt_ts, price=px, size=sz)
