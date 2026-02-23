"""Compatibility shim: use crypto-analyzer backtest or python -m crypto_analyzer backtest."""

from crypto_analyzer.cli.backtest import main

if __name__ == "__main__":
    raise SystemExit(main())
