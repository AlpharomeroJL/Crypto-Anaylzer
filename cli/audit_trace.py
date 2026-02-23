"""Compatibility shim: use crypto-analyzer audit_trace or python -m crypto_analyzer audit_trace."""

from crypto_analyzer.cli.audit_trace import main

if __name__ == "__main__":
    raise SystemExit(main())
