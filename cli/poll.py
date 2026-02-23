"""Compatibility shim: use crypto-analyzer poll or python -m crypto_analyzer poll."""

from crypto_analyzer.cli.poll import main

if __name__ == "__main__":
    raise SystemExit(main())
