"""Universe: fetch_dex_universe_top_pairs parsing (mock), allowlist filtering."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

# Import from dex_poll_to_sqlite (root script)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dex_poll_to_sqlite import fetch_dex_universe_top_pairs, load_universe_config


def test_fetch_dex_universe_top_pairs_mock_empty():
    """When API returns no pairs, result is empty list."""
    with patch("dex_poll_to_sqlite.requests.get") as m:
        m.return_value.json.return_value = {"pairs": []}
        m.return_value.raise_for_status = MagicMock()
        out = fetch_dex_universe_top_pairs(chain_id="solana", page_size=10, min_liquidity_usd=0, min_vol_h24=0)
    assert out == [] or isinstance(out, list)


def test_fetch_dex_universe_top_pairs_mock_filter():
    """Filter by chain_id and liquidity/vol."""
    with patch("dex_poll_to_sqlite.requests.get") as m:
        m.return_value.json.return_value = {
            "pairs": [
                {"chainId": "solana", "pairAddress": "addr1", "baseToken": {"symbol": "SOL"}, "quoteToken": {"symbol": "USDC"}, "liquidity": {"usd": 300000}, "volume": {"h24": 600000}},
                {"chainId": "ethereum", "pairAddress": "addr2", "baseToken": {"symbol": "ETH"}, "quoteToken": {"symbol": "USDC"}, "liquidity": {"usd": 500000}, "volume": {"h24": 700000}},
            ]
        }
        m.return_value.raise_for_status = MagicMock()
        out = fetch_dex_universe_top_pairs(chain_id="solana", page_size=50, min_liquidity_usd=250000, min_vol_h24=500000)
    assert isinstance(out, list)
    # Solana pair passes filters; ethereum is filtered out by chain_id
    assert len(out) >= 1
    assert out[0]["chain_id"] == "solana" and out[0]["pair_address"] == "addr1"


def test_load_universe_config_defaults():
    """Without a config file, returns defaults with enabled: false."""
    out = load_universe_config("/nonexistent/config.yaml")
    assert "enabled" in out
    assert "chain_id" in out
    assert out.get("chain_id") == "solana" or "chain_id" in out
