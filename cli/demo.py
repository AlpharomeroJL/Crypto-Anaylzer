"""Compatibility shim: use crypto-analyzer demo or python -m crypto_analyzer demo."""

from crypto_analyzer.cli.demo import main

if __name__ == "__main__":
    raise SystemExit(main())
