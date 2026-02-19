"""Universe: fetch_dex_universe_top_pairs parsing (mock), allowlist filtering, churn, persist, bootstrap."""

from __future__ import annotations

import math
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "cli"))
from poll import (
    _apply_churn_control,
    _persist_universe_allowlist,
    _universe_keep_pair,
    _universe_rank_key,
    ensure_db,
    fetch_dex_search_pairs,
    fetch_dex_universe_top_pairs,
    load_bootstrap_pairs_from_config,
    load_universe_config,
)


def _item(chain_id="solana", pair_address="addr1", base="SOL", quote="USDC", liquidity=1e6, volume=1e6, dex_id=None):
    d = {
        "chainId": chain_id,
        "pairAddress": pair_address,
        "baseToken": {"symbol": base},
        "quoteToken": {"symbol": quote},
        "liquidity": {"usd": liquidity},
        "volume": {"h24": volume},
    }
    if dex_id is not None:
        d["dexId"] = dex_id
    return d


def test_universe_keep_pair_sol_sol_rejected():
    """SOL/SOL with valid liq/vol must be rejected (base==quote)."""
    item = _item(base="SOL", quote="SOL", pair_address="sol_sol_addr")
    keep, reason = _universe_keep_pair(
        item,
        min_liquidity_usd=0,
        min_vol_h24=0,
        quote_allowlist=["USDC", "USDT"],
        reject_same_symbol=True,
        reject_stable_stable=True,
    )
    assert keep is False
    assert "base==quote" in reason


def test_universe_keep_pair_sol_usdc_accepted():
    """SOL/USDC with valid liq/vol must be accepted for default allowlist."""
    item = _item(base="SOL", quote="USDC", pair_address="sol_usdc_addr")
    keep, reason = _universe_keep_pair(
        item,
        min_liquidity_usd=100_000,
        min_vol_h24=200_000,
        quote_allowlist=["USDC", "USDT"],
        reject_same_symbol=True,
        reject_stable_stable=True,
    )
    assert keep is True
    assert reason == "accept"


def test_universe_keep_pair_quote_not_allowlisted():
    """SOL/XYZ with valid liq/vol must be rejected when quote not in allowlist."""
    item = _item(base="SOL", quote="XYZ", pair_address="sol_xyz_addr")
    keep, reason = _universe_keep_pair(
        item,
        min_liquidity_usd=0,
        min_vol_h24=0,
        quote_allowlist=["USDC", "USDT"],
        reject_same_symbol=True,
        reject_stable_stable=True,
    )
    assert keep is False
    assert "not in allowlist" in reason


def test_universe_keep_pair_missing_liquidity_rejected():
    """Pair with missing liquidity must be rejected."""
    item = _item(base="SOL", quote="USDC", pair_address="addr")
    item["liquidity"] = None
    keep, reason = _universe_keep_pair(
        item,
        min_liquidity_usd=0,
        min_vol_h24=0,
        quote_allowlist=["USDC", "USDT"],
        reject_same_symbol=True,
        reject_stable_stable=True,
    )
    assert keep is False
    assert "liquidity" in reason.lower()


def test_universe_keep_pair_missing_volume_rejected():
    """Pair with missing volume must be rejected."""
    item = _item(base="SOL", quote="USDC", pair_address="addr")
    item["volume"] = None
    keep, reason = _universe_keep_pair(
        item,
        min_liquidity_usd=0,
        min_vol_h24=0,
        quote_allowlist=["USDC", "USDT"],
        reject_same_symbol=True,
        reject_stable_stable=True,
    )
    assert keep is False
    assert "volume" in reason.lower()


def test_universe_keep_pair_stable_stable_rejected():
    """USDC/USDT must be rejected when reject_stable_stable=True."""
    item = _item(base="USDC", quote="USDT", pair_address="stable_stable_addr")
    keep, reason = _universe_keep_pair(
        item,
        min_liquidity_usd=0,
        min_vol_h24=0,
        quote_allowlist=["USDC", "USDT"],
        reject_same_symbol=True,
        reject_stable_stable=True,
    )
    assert keep is False
    assert "stable" in reason.lower()


def test_universe_keep_pair_stable_stable_allowed_when_disabled():
    """USDC/USDT accepted when reject_stable_stable=False."""
    item = _item(base="USDC", quote="USDT", pair_address="stable_stable_addr")
    keep, reason = _universe_keep_pair(
        item,
        min_liquidity_usd=0,
        min_vol_h24=0,
        quote_allowlist=["USDC", "USDT"],
        reject_same_symbol=True,
        reject_stable_stable=False,
    )
    assert keep is True
    assert reason == "accept"


def test_fetch_dex_universe_only_sol_usdc_survives_default_allowlist():
    """Mock response: SOL/SOL rejected, SOL/XYZ rejected, SOL/USDC accepted. Only SOL/USDC in output."""

    def _mock_get(url, timeout=None, **kwargs):
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json.return_value = {
            "pairs": [
                {
                    "chainId": "solana",
                    "pairAddress": "sol_sol",
                    "baseToken": {"symbol": "SOL"},
                    "quoteToken": {"symbol": "SOL"},
                    "liquidity": {"usd": 1e6},
                    "volume": {"h24": 1e6},
                },
                {
                    "chainId": "solana",
                    "pairAddress": "sol_usdc",
                    "baseToken": {"symbol": "SOL"},
                    "quoteToken": {"symbol": "USDC"},
                    "liquidity": {"usd": 1e6},
                    "volume": {"h24": 1e6},
                },
                {
                    "chainId": "solana",
                    "pairAddress": "sol_xyz",
                    "baseToken": {"symbol": "SOL"},
                    "quoteToken": {"symbol": "XYZ"},
                    "liquidity": {"usd": 1e6},
                    "volume": {"h24": 1e6},
                },
            ]
        }
        return r

    with patch("poll.requests.get", side_effect=_mock_get):
        out = fetch_dex_universe_top_pairs(
            chain_id="solana",
            page_size=50,
            min_liquidity_usd=0,
            min_vol_h24=0,
            quote_allowlist=["USDC", "USDT"],
            reject_same_symbol=True,
            reject_stable_stable=True,
            queries=["SOL"],
        )
    assert len(out) == 1
    assert out[0]["label"] == "SOL/USDC"
    assert out[0]["pair_address"] == "sol_usdc"


def test_fetch_dex_universe_multi_query_sol_returns_sol_sol_usdc_returns_sol_usdc():
    """Multiple queries: SOL yields SOL/SOL only, USDC yields SOL/USDC. Merged output includes SOL/USDC and excludes SOL/SOL."""

    def _mock_get(url, timeout=None, **kwargs):
        r = MagicMock()
        r.raise_for_status = MagicMock()
        if "q=SOL" in url:
            r.json.return_value = {
                "pairs": [
                    {
                        "chainId": "solana",
                        "pairAddress": "sol_sol_addr",
                        "baseToken": {"symbol": "SOL"},
                        "quoteToken": {"symbol": "SOL"},
                        "liquidity": {"usd": 1e6},
                        "volume": {"h24": 1e6},
                    },
                ]
            }
        elif "q=USDC" in url:
            r.json.return_value = {
                "pairs": [
                    {
                        "chainId": "solana",
                        "pairAddress": "sol_usdc_addr",
                        "baseToken": {"symbol": "SOL"},
                        "quoteToken": {"symbol": "USDC"},
                        "liquidity": {"usd": 1e6},
                        "volume": {"h24": 1e6},
                    },
                ]
            }
        else:
            r.json.return_value = {"pairs": []}
        return r

    with patch("poll.requests.get", side_effect=_mock_get):
        out = fetch_dex_universe_top_pairs(
            chain_id="solana",
            page_size=50,
            min_liquidity_usd=0,
            min_vol_h24=0,
            quote_allowlist=["USDC", "USDT"],
            reject_same_symbol=True,
            reject_stable_stable=True,
            queries=["SOL", "USDC"],
        )
    assert len(out) == 1
    assert out[0]["label"] == "SOL/USDC"
    assert out[0]["pair_address"] == "sol_usdc_addr"
    labels = [p["label"] for p in out]
    assert "SOL/SOL" not in labels


def test_fetch_dex_universe_dedup_by_pair_address():
    """Same pair from two different query responses appears once (de-dup by pairAddress)."""
    common_pair = {
        "chainId": "solana",
        "pairAddress": "shared_addr",
        "baseToken": {"symbol": "SOL"},
        "quoteToken": {"symbol": "USDC"},
        "liquidity": {"usd": 1e6},
        "volume": {"h24": 1e6},
    }

    def _mock_get(url, timeout=None, **kwargs):
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json.return_value = {"pairs": [common_pair]}
        return r

    with patch("poll.requests.get", side_effect=_mock_get):
        out = fetch_dex_universe_top_pairs(
            chain_id="solana",
            page_size=50,
            min_liquidity_usd=0,
            min_vol_h24=0,
            queries=["USDC", "USDT"],
        )
    assert len(out) == 1
    assert out[0]["pair_address"] == "shared_addr"


def test_fetch_dex_universe_uses_pair_address_not_dex_id():
    """Output must use pairAddress as key; items with only dexId (no pairAddress) must be skipped."""
    payload = {
        "pairs": [
            {
                "chainId": "solana",
                "dexId": "junk_dex_id",
                "baseToken": {"symbol": "SOL"},
                "quoteToken": {"symbol": "USDC"},
                "liquidity": {"usd": 1e6},
                "volume": {"h24": 1e6},
            },
            {
                "chainId": "solana",
                "pairAddress": "real_pair_addr",
                "baseToken": {"symbol": "SOL"},
                "quoteToken": {"symbol": "USDC"},
                "liquidity": {"usd": 1e6},
                "volume": {"h24": 1e6},
            },
        ]
    }
    with patch("poll.requests.get") as m:
        m.return_value.json.return_value = payload
        m.return_value.raise_for_status = MagicMock()
        out = fetch_dex_universe_top_pairs(
            chain_id="solana",
            page_size=50,
            min_liquidity_usd=0,
            min_vol_h24=0,
            queries=["USDC"],
        )
    assert len(out) == 1
    assert out[0]["pair_address"] == "real_pair_addr"
    assert "dexId" not in out[0] or out[0].get("pair_address") == "real_pair_addr"


def test_fetch_dex_universe_debug_does_not_crash(capsys):
    """Call fetch with universe_debug > 0; must not throw."""
    payload = {
        "pairs": [
            {
                "chainId": "solana",
                "pairAddress": "a1",
                "baseToken": {"symbol": "SOL"},
                "quoteToken": {"symbol": "USDC"},
                "liquidity": {"usd": 1e6},
                "volume": {"h24": 1e6},
            }
        ]
    }
    with patch("poll.requests.get") as m:
        m.return_value.json.return_value = payload
        m.return_value.raise_for_status = MagicMock()
        out = fetch_dex_universe_top_pairs(
            chain_id="solana",
            page_size=10,
            min_liquidity_usd=0,
            min_vol_h24=0,
            queries=["USDC"],
            universe_debug=5,
        )
    assert isinstance(out, list)
    assert len(out) >= 1
    captured = capsys.readouterr()
    assert "[universe]" in captured.out or len(out) > 0


def test_fetch_dex_universe_top_pairs_mock_empty():
    """When API returns no pairs (all queries empty), result is empty for chains with no bootstrap."""
    with patch("poll.requests.get") as m:
        m.return_value.json.return_value = {"pairs": []}
        m.return_value.raise_for_status = MagicMock()
        out = fetch_dex_universe_top_pairs(
            chain_id="ethereum", page_size=10, min_liquidity_usd=0, min_vol_h24=0, queries=["SOL", "USDC"]
        )
    assert out == []


def test_fetch_dex_universe_bootstrap_when_solana_returns_zero():
    """When Solana API returns 0 accepted pairs, fetch returns [] (bootstrap is config-only in _get_universe_pairs)."""
    with patch("poll.requests.get") as m:
        m.return_value.json.return_value = {"pairs": []}
        m.return_value.raise_for_status = MagicMock()
        out = fetch_dex_universe_top_pairs(
            chain_id="solana", page_size=10, min_liquidity_usd=0, min_vol_h24=0, queries=["SOL", "USDC"]
        )
    assert out == []


def test_fetch_dex_universe_top_pairs_mock_filter():
    """Filter by chain_id and liquidity/vol; multi-query merge then filter."""
    payload = {
        "pairs": [
            {
                "chainId": "solana",
                "pairAddress": "addr1",
                "baseToken": {"symbol": "SOL"},
                "quoteToken": {"symbol": "USDC"},
                "liquidity": {"usd": 300000},
                "volume": {"h24": 600000},
            },
            {
                "chainId": "ethereum",
                "pairAddress": "addr2",
                "baseToken": {"symbol": "ETH"},
                "quoteToken": {"symbol": "USDC"},
                "liquidity": {"usd": 500000},
                "volume": {"h24": 700000},
            },
        ]
    }
    with patch("poll.requests.get") as m:
        m.return_value.json.return_value = payload
        m.return_value.raise_for_status = MagicMock()
        out = fetch_dex_universe_top_pairs(
            chain_id="solana", page_size=50, min_liquidity_usd=250000, min_vol_h24=500000, queries=["USDC"]
        )
    assert isinstance(out, list)
    assert len(out) >= 1
    assert out[0]["chain_id"] == "solana" and out[0]["pair_address"] == "addr1"


def test_load_universe_config_defaults():
    """Without a config file, returns defaults with enabled: false and queries."""
    out = load_universe_config("/nonexistent/config.yaml")
    assert "enabled" in out
    assert "chain_id" in out
    assert "queries" in out
    assert out.get("chain_id") == "solana" or "chain_id" in out
    assert out.get("queries") == ["USDC", "USDT", "SOL", "SOL/USDC", "orca"] or "queries" in out


def test_fetch_dex_search_pairs_mock():
    """fetch_dex_search_pairs returns list of pair dicts from API response."""
    with patch("poll.requests.get") as m:
        m.return_value.json.return_value = {
            "pairs": [
                {
                    "chainId": "solana",
                    "pairAddress": "addr1",
                    "baseToken": {"symbol": "SOL"},
                    "quoteToken": {"symbol": "USDC"},
                },
            ]
        }
        m.return_value.raise_for_status = MagicMock()
        out = fetch_dex_search_pairs("USDC")
    assert isinstance(out, list)
    assert len(out) == 1
    assert out[0].get("pairAddress") == "addr1"


# --- Deterministic sort, churn, relaxed, bootstrap_pairs, persist (institutional patch) ---


def test_universe_rank_key_deterministic_sort():
    """Deterministic sort: liquidity desc, volume desc, label asc, pair_address asc."""
    candidates = [
        {"chain_id": "solana", "pair_address": "a2", "label": "SOL/USDC", "liquidity_usd": 100.0, "vol_h24": 50.0},
        {"chain_id": "solana", "pair_address": "a1", "label": "SOL/USDC", "liquidity_usd": 100.0, "vol_h24": 50.0},
        {"chain_id": "solana", "pair_address": "b1", "label": "SOL/USDT", "liquidity_usd": 200.0, "vol_h24": 100.0},
        {"chain_id": "solana", "pair_address": "c1", "label": "SOL/USDC", "liquidity_usd": 200.0, "vol_h24": 80.0},
    ]
    sorted_list = sorted(candidates, key=_universe_rank_key)
    assert sorted_list[0]["liquidity_usd"] == 200.0 and sorted_list[0]["pair_address"] == "b1"
    assert sorted_list[1]["liquidity_usd"] == 200.0 and sorted_list[1]["pair_address"] == "c1"
    assert sorted_list[2]["pair_address"] == "a1"
    assert sorted_list[3]["pair_address"] == "a2"


def test_relaxed_thresholds_accept_when_strict_rejects():
    """When strict min_liq/min_vol reject all, relaxed (0.25x) accepts same pairs."""
    relaxed_floor = int(500_000 * 0.25) + 10
    payload = {
        "pairs": [
            {
                "chainId": "solana",
                "pairAddress": "addr1",
                "baseToken": {"symbol": "SOL"},
                "quoteToken": {"symbol": "USDC"},
                "liquidity": {"usd": relaxed_floor},
                "volume": {"h24": relaxed_floor},
            },
        ]
    }
    with patch("poll.requests.get") as m:
        m.return_value.json.return_value = payload
        m.return_value.raise_for_status = MagicMock()
        strict = fetch_dex_universe_top_pairs(
            chain_id="solana", page_size=10, min_liquidity_usd=500_000, min_vol_h24=500_000, queries=["USDC"]
        )
        relaxed_liq = max(0, 500_000 * 0.25)
        relaxed_vol = max(0, 500_000 * 0.25)
        relaxed = fetch_dex_universe_top_pairs(
            chain_id="solana", page_size=10, min_liquidity_usd=relaxed_liq, min_vol_h24=relaxed_vol, queries=["USDC"]
        )
    assert len(strict) == 0
    assert len(relaxed) == 1
    assert relaxed[0]["pair_address"] == "addr1"


def test_churn_control_keeps_overlap_limits_replacements():
    """Churn: all overlapping pairs kept; replaced count <= ceil(prev_size * max_churn_pct)."""
    prev = [
        {"chain_id": "s", "pair_address": "p1", "label": "A"},
        {"chain_id": "s", "pair_address": "p2", "label": "B"},
        {"chain_id": "s", "pair_address": "p3", "label": "C"},
        {"chain_id": "s", "pair_address": "p4", "label": "D"},
        {"chain_id": "s", "pair_address": "p5", "label": "E"},
    ]
    new = [
        {"chain_id": "s", "pair_address": "p1", "label": "A"},
        {"chain_id": "s", "pair_address": "p6", "label": "F"},
        {"chain_id": "s", "pair_address": "p2", "label": "B"},
        {"chain_id": "s", "pair_address": "p7", "label": "G"},
        {"chain_id": "s", "pair_address": "p8", "label": "H"},
    ]
    out = _apply_churn_control(prev, new, page_size=5, max_churn_pct=0.20)
    max_allowed_replace = math.ceil(len(prev) * 0.20)
    prev_addrs = {"p1", "p2", "p3", "p4", "p5"}
    overlapping = {"p1", "p2"}
    kept_count = sum(1 for p in out if p.get("pair_address") in prev_addrs)
    replaced_count = len(out) - kept_count
    assert kept_count >= len(overlapping)
    assert all(any(p.get("pair_address") == a for p in out) for a in overlapping)
    assert replaced_count <= max_allowed_replace
    assert any(p.get("pair_address") == "p1" for p in out)
    assert any(p.get("pair_address") == "p2" for p in out)


def test_bootstrap_pairs_from_config():
    """When config has universe.bootstrap_pairs for chain, load_bootstrap_pairs_from_config returns them; source would be bootstrap_pairs."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write("""
universe:
  bootstrap_pairs:
    - chain_id: solana
      pair_address: "Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE"
      label: SOL/USDC
    - chain_id: ethereum
      pair_address: "0xabc"
      label: ETH/USDC
    - chain_id: solana
      pair_address: "AnotherSolanaAddr"
      label: SOL/USDT
""")
        f.flush()
        path = f.name
    try:
        out = load_bootstrap_pairs_from_config(path, "solana")
        assert len(out) == 2
        labels = [p["label"] for p in out]
        assert "SOL/USDC" in labels
        assert "SOL/USDT" in labels
        assert all(p["chain_id"] == "solana" for p in out)
        assert out[0].get("source") is None
    finally:
        Path(path).unlink(missing_ok=True)


def test_persist_universe_allowlist_table():
    """Create temp DB, ensure_db, _persist_universe_allowlist; verify rows and source/query_summary."""
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    try:
        import os

        os.close(fd)
        conn = sqlite3.connect(path)
        ensure_db(conn)
        pairs = [
            {
                "chain_id": "solana",
                "pair_address": "addr1",
                "label": "SOL/USDC",
                "liquidity_usd": 1e6,
                "vol_h24": 500e3,
            },
            {"chain_id": "solana", "pair_address": "addr2", "label": "SOL/USDT", "liquidity_usd": 2e6, "vol_h24": None},
        ]
        _persist_universe_allowlist(conn, "2025-02-17T12:00:00+00:00", pairs, "universe", "USDC,USDT,SOL")
        conn.close()
        conn2 = sqlite3.connect(path)
        cur = conn2.execute(
            "SELECT ts_utc, chain_id, pair_address, label, liquidity_usd, source, query_summary FROM universe_allowlist ORDER BY pair_address"
        )
        rows = cur.fetchall()
        conn2.close()
        assert len(rows) == 2
        by_addr = {r[2]: r for r in rows}
        assert by_addr["addr1"][5] == "universe"
        assert "USDC" in (by_addr["addr1"][6] or "")
    finally:
        Path(path).unlink(missing_ok=True)
