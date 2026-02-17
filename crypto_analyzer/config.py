"""
Load config from config.yaml with optional env overrides.
Single source of truth for DB path, table, price column, filters, and defaults.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

# Defaults if no YAML or env
_DEFAULTS = {
    "db": {
        "path": "dex_data.sqlite",
        "table": "sol_monitor_snapshots",
        "price_column": "dex_price_usd",
        "timezone": "UTC",
    },
    "defaults": {"freq": "5min", "window": 288},
    "filters": {
        "min_liquidity_usd": 250_000,
        "min_vol_h24": 500_000,
        "min_bars": 48,
        "exclude_stable_pairs": True,
    },
    "bars_freqs": ["5min", "15min", "1h", "1D"],
    "factor_symbol": "BTC",
}


def _config_yaml_path() -> Path:
    """Config.yaml lives at repo root (parent of package dir)."""
    return Path(__file__).resolve().parent.parent / "config.yaml"


def _load_yaml() -> dict:
    try:
        import yaml
    except ImportError:
        return {}
    config_path = _config_yaml_path()
    if not config_path.exists():
        return {}
    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _env_overrides() -> dict:
    overrides: dict = {}
    path = os.environ.get("CRYPTO_DB_PATH")
    if path:
        overrides.setdefault("db", {})["path"] = path
    table = os.environ.get("CRYPTO_TABLE")
    if table:
        overrides.setdefault("db", {})["table"] = table
    price_col = os.environ.get("CRYPTO_PRICE_COLUMN")
    if price_col:
        overrides.setdefault("db", {})["price_column"] = price_col
    return overrides


def get_config() -> dict:
    """Return merged config: defaults <- config.yaml <- env."""
    merged = _deep_merge(_DEFAULTS, _load_yaml())
    merged = _deep_merge(merged, _env_overrides())
    return merged


# Convenience accessors
def db_path() -> str:
    return get_config()["db"]["path"]


def db_table() -> str:
    return get_config()["db"]["table"]


def price_column() -> str:
    return get_config()["db"]["price_column"]


def timezone() -> str:
    return get_config()["db"]["timezone"]


def default_freq() -> str:
    return get_config()["defaults"]["freq"]


def default_window() -> int:
    return get_config()["defaults"]["window"]


def min_liquidity_usd() -> float:
    return float(get_config()["filters"]["min_liquidity_usd"])


def min_vol_h24() -> float:
    return float(get_config()["filters"]["min_vol_h24"])


def min_bars() -> int:
    return int(get_config()["filters"]["min_bars"])


def exclude_stable_pairs() -> bool:
    return bool(get_config()["filters"]["exclude_stable_pairs"])


def bars_freqs() -> list:
    return list(get_config().get("bars_freqs", _DEFAULTS["bars_freqs"]))


def factor_symbol() -> str:
    return str(get_config().get("factor_symbol", _DEFAULTS["factor_symbol"]))


STABLE_SYMBOLS = frozenset({"USDC", "USDT", "DAI", "BUSD", "TUSD", "USDP", "FRAX"})
FACTOR_SYMBOLS = frozenset({"BTC", "WBTC", "CBBTC"})


def is_btc_pair(label: str) -> bool:
    """True if label (e.g. 'BTC/USDC' or 'SOL/WBTC') contains a factor symbol."""
    if not label:
        return False
    upper = label.upper().replace("/", " ").split()
    return any(s in FACTOR_SYMBOLS for s in upper)
