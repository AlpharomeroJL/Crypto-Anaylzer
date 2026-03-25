---
name: add-provider
description: Add a new CEX or DEX provider to the Crypto-Analyzer platform. Enforce the repo wiring sequence: implement the provider protocol, register it in defaults, update config keys, add tests with mocked HTTP, and optionally add a short docs snippet. Use when adding a new exchange, data source, or provider.
---

# Add A New Provider

## Wiring Sequence

### 1. Implement the provider
- For CEX spot data, add a new file under `crypto_analyzer/providers/cex/<name>.py`.
- For DEX data, add a new file under `crypto_analyzer/providers/dex/<name>.py`.
- Implement the correct protocol, expose a stable `provider_name`, and return the repo DTOs (`SpotQuote` or `DexSnapshot`).
- Do not add retry or circuit-breaker behavior inside the provider. The chain handles resilience with `resilient_call()`.

### 2. Register it in defaults
- Import the provider in `crypto_analyzer/providers/defaults.py`.
- Register it with a stable lowercase key using `registry.register_spot(...)` or `registry.register_dex(...)`.

### 3. Update config
- Add the provider key to `config.yaml` under `providers.spot_priority` or `providers.dex_priority`.
- If the provider needs extra settings, add new keys under a clearly named section.
- Do not rename or remove existing config keys.

### 4. Add tests
- Add or update tests under `tests/`.
- Mock HTTP at the module where `requests` is used, for example `crypto_analyzer.providers.cex.my_provider.requests.get`.
- Cover happy path parsing and failure behavior such as 429s, timeouts, or malformed payloads.
- Keep tests offline. No live network calls.

### 5. Add a short docs note
- Optionally add one short paragraph or bullet to `CONTRIBUTING.md` or `README.md` so the provider is discoverable.

## Checklist Before Finishing
- [ ] Provider implementation added in `cex/` or `dex/`
- [ ] Registered in `defaults.py`
- [ ] Added to `config.yaml`
- [ ] Tests added with mocked HTTP
- [ ] Optional docs snippet added

## Output
- Files changed
- Commands to run: `python -m pytest -q`, `ruff check .`, and optionally one poll cycle
- What to look for: tests pass, config loads, and the provider appears in the configured priority chain

