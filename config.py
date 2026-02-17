# Thin wrapper: re-export from package so "from config import db_path" works.
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from crypto_analyzer.config import (
    get_config,
    db_path,
    db_table,
    price_column,
    timezone,
    default_freq,
    default_window,
    min_liquidity_usd,
    min_vol_h24,
    min_bars,
    exclude_stable_pairs,
    bars_freqs,
    factor_symbol,
    STABLE_SYMBOLS,
    FACTOR_SYMBOLS,
    is_btc_pair,
)
