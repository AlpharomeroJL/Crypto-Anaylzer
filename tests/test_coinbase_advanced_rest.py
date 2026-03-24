"""Tests for Coinbase Advanced Trade public REST client (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import MagicMock

from crypto_analyzer.providers.coinbase_advanced.rest_client import CoinbaseAdvancedRestClient


def test_get_public_candles_parses_rows() -> None:
    sess = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {
        "candles": [
            {
                "start": "1700000000",
                "open": "100.0",
                "high": "101.0",
                "low": "99.0",
                "close": "100.5",
                "volume": "12.5",
            }
        ]
    }
    resp.raise_for_status = MagicMock()
    sess.get.return_value = resp

    c = CoinbaseAdvancedRestClient(session=sess)
    rows = c.get_public_candles("BTC-USD", start_sec=1700000000, end_sec=1700003600, granularity="ONE_HOUR")
    assert len(rows) == 1
    assert rows[0].start_unix == 1700000000
    assert rows[0].close == 100.5
    assert rows[0].volume == 12.5
    sess.get.assert_called_once()
    call_kw = sess.get.call_args
    assert "BTC-USD" in call_kw[0][0]


def test_list_public_products_builds_query_string() -> None:
    sess = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {"products": [{"product_id": "BTC-USD", "price": "1"}]}
    resp.raise_for_status = MagicMock()
    sess.get.return_value = resp

    c = CoinbaseAdvancedRestClient(session=sess)
    out = c.list_public_products(product_ids=["BTC-USD", "ETH-USD"])
    assert "products" in out
    url = sess.get.call_args[0][0]
    assert "product_ids=BTC-USD" in url
    assert "product_ids=ETH-USD" in url


def test_iter_public_candles_1h_chunks() -> None:
    sess = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {"candles": []}
    resp.raise_for_status = MagicMock()
    sess.get.return_value = resp

    c = CoinbaseAdvancedRestClient(session=sess)
    # 2 hours span -> one API window
    c.iter_public_candles_1h("BTC-USD", start_sec=1000, end_sec=1000 + 7200)
    assert sess.get.called
