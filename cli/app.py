"""Compatibility shim: use crypto-analyzer streamlit or streamlit run crypto_analyzer/cli/app.py."""

from crypto_analyzer.cli.app import main

if __name__ == "__main__":
    raise SystemExit(main())
