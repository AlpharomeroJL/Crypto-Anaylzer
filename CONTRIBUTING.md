# Contributing

## Development Setup

```bash
# Clone and set up virtual environment
git clone <repo-url> && cd crypto-analyzer
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
pip install -e ".[dev]"

# Verify everything works
python -m pytest -q
.\scripts\run.ps1 doctor
```

## Running Tests

```bash
# Full suite (200 tests)
python -m pytest -q

# Specific test file
python -m pytest tests/test_provider_chain.py -v

# With coverage (if installed)
python -m pytest --cov=crypto_analyzer -q
```

All tests must pass before submitting changes. No test may make live network calls — use mocked HTTP responses.

## Code Style

- **Type hints** at all public function boundaries (parameters and return types)
- **Docstrings** on all public classes and functions (module-level docstrings on every file)
- **Logging** via `logging.getLogger(__name__)` — never bare `print()` in library code (CLI scripts may use `print()`)
- **Imports** organized: stdlib → third-party → local, with blank line separators
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE` for constants

## Adding a New Provider

The provider architecture is plugin-based. To add a new data source:

### 1. Implement the Protocol

For CEX spot prices, create a class implementing `SpotPriceProvider`:

```python
# crypto_analyzer/providers/cex/my_exchange.py
from ..base import SpotQuote, ProviderStatus

class MyExchangeSpotProvider:
    @property
    def provider_name(self) -> str:
        return "my_exchange"

    def get_spot(self, symbol: str) -> SpotQuote:
        # Fetch from the public API
        # Return a SpotQuote with provider_name set
        ...
```

For DEX sources, implement `DexSnapshotProvider` with `get_snapshot()` and `search_pairs()`.

### 2. Register in Defaults

Add your provider to `crypto_analyzer/providers/defaults.py`:

```python
from .cex.my_exchange import MyExchangeSpotProvider

def create_default_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register_spot("coinbase", CoinbaseSpotProvider)
    registry.register_spot("kraken", KrakenSpotProvider)
    registry.register_spot("my_exchange", MyExchangeSpotProvider)
    ...
```

### 3. Add to Config

```yaml
# config.yaml
providers:
  spot_priority: ["coinbase", "my_exchange", "kraken"]
```

### 4. Write Tests

Add a test file `tests/test_my_exchange_provider.py` with:
- Mocked HTTP response parsing
- Error handling (429, timeouts, malformed responses)
- Integration with the provider chain

### 5. No Live Network in Tests

All HTTP calls must be mocked using `unittest.mock.patch`. Example:

```python
@patch("crypto_analyzer.providers.cex.my_exchange.requests.get")
def test_my_exchange(self, mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"price": "50000.0"},
    )
    provider = MyExchangeSpotProvider()
    quote = provider.get_spot("BTC")
    assert quote.price_usd == 50000.0
```

## Project Structure Conventions

- **Core library** lives in `crypto_analyzer/` — importable as a package
- **CLI entry points** live in `cli/` — runnable scripts
- **Tests** live in `tests/` — pytest discovers them automatically
- **Provider implementations** live in `crypto_analyzer/providers/cex/` or `crypto_analyzer/providers/dex/`
- **Database logic** lives in `crypto_analyzer/db/`

## Research-Only Boundary

This platform is strictly research-only. The following are prohibited:
- Trading execution or order submission
- API key storage or authenticated endpoints
- Connection to any broker or execution venue
- Position management or risk management for live capital

**Enforced in CI:** `.\scripts\run.ps1 verify` runs a research-only guardrail that scans source for forbidden keywords (order, submit, broker, exchange account, api key, secret, withdraw, etc.). Any match fails verify with a clear message. See `crypto_analyzer.spec.validate_research_only_boundary` and the keyword list in `spec.py`.

## Private conversion (research → trading bot)

The repo is designed so a **private** execution layer can consume it as a dependency (submodule or vendored) without forking. The OSS code defines the execution boundary (`OrderIntent`, `signal_to_order_intent`) but never submits orders or holds keys. See [Private Conversion Plan](docs/private_conversion.md) for layout and responsibilities.

## Commit Messages

Use conventional-style messages:
- `feat: add binance spot provider`
- `fix: handle kraken empty result gracefully`
- `test: add circuit breaker recovery test`
- `docs: update provider extension guide`
- `refactor: extract retry logic to resilience module`
