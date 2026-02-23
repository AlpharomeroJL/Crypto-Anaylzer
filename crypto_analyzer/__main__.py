"""Entrypoint for python -m crypto_analyzer and installed crypto-analyzer CLI."""

from __future__ import annotations

from .cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
