# Contributing

## Development Setup

**Canonical (uv, recommended):**

```powershell
git clone <repo-url> && cd Crypto-Anaylzer
uv sync --frozen
uv run python -m crypto_analyzer --help
uv run crypto-analyzer doctor
```

**Pip fallback:**

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python -m crypto_analyzer --help
crypto-analyzer doctor
```

Optional UI (dashboard/streamlit): `uv sync --frozen --extra ui` or `pip install -e ".[dev,ui]"`.

## Local verification (canonical commands)

Run from repo root. These match CI exactly.

```powershell
uv sync --frozen
uv run python -m pytest -m "not slow and not network" -q --tb=short
uv run ruff check crypto_analyzer cli tests tools
uv run ruff format --check crypto_analyzer cli tests tools
uv run python tools/check_md_links.py
uv run python tools/check_import_boundaries.py
uv run crypto-analyzer doctor --ci
uv run crypto-analyzer smoke --ci
```

Use `python -m` if not using uv: `python -m pytest -m "not slow and not network" -q --tb=short`, etc.

## Pre-commit

Install hooks for fast local checks (ruff, trailing whitespace, end-of-file, check-yaml):

```powershell
uv run pre-commit install
# or: pip install pre-commit && pre-commit install
```

Then `git commit` will run ruff and format. Run manually: `pre-commit run --all-files`.

## Running Tests

- **Default (CI and docs):** `uv run python -m pytest -m "not slow and not network" -q --tb=short` — skips slow and network-marked tests.
- **Full suite:** `uv run python -m pytest -q`
- **Include slow:** `uv run python -m pytest -m "not slow" -q` or drop the marker.

All tests must pass before submitting. No test may make live network calls unless marked `@pytest.mark.network` (and those are excluded from default run). Use mocked HTTP in tests.

## Offline / restricted network

To run without network (e.g. air-gapped or wheelhouse):

1. **Wheelhouse (pip):** From a machine with network, download wheels:  
   `pip download -r requirements.txt -d wheelhouse` (or use `pyproject.toml` and extras). Copy `wheelhouse/` and install with `pip install --no-index --find-links wheelhouse -e ".[dev]"`.
2. **uv:** Use `uv sync --frozen --offline` when lock and cache are already present.
3. **CI:** Test jobs do not require network; `smoke --ci` and `demo-lite` are explicitly no-network. Only lock/install steps and optional security audit use network.

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
