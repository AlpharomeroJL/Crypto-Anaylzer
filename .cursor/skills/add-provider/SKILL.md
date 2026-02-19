---
name: add-provider
description: Add a new CEX or DEX provider to the Crypto-Analyzer platform. Enforces wiring sequence: implement protocol, register in defaults, add config keys, add tests with mocked HTTP, optional docs snippet. Use when the user wants to add a new exchange, data source, or provider.
---

# Add a New Provider

## Wiring Sequence (Do in Order)

### 1. Implement provider (cex/ or dex/)
- **CEX spot**: New file under `crypto_analyzer/providers/cex/<name>.py`. Implement `SpotPriceProvider`: `provider_name` property, `get_spot(symbol) -> SpotQuote`. Use frozen `SpotQuote` from `..base`; set `provider_name`, `fetched_at_utc`; on invalid/rate-limit return DEGRADED or raise so chain can retry/fallback.
- **DEX**: New file under `crypto_analyzer/providers/dex/<name>.py`. Implement `DexSnapshotProvider`: `provider_name`, `get_snapshot(chain_id, pair_address) -> DexSnapshot`, `search_pairs(query, chain_id) -> list[dict]`. Use `DexSnapshot` from `..base`.
- Do **not** add retry/circuit breaker inside the provider; the chain uses `resilient_call()`.

### 2. Register in defaults.py
- In `crypto_analyzer/providers/defaults.py`: import the new class and call `registry.register_spot("provider_key", MySpotProvider)` or `registry.register_dex("provider_key", MyDexProvider)`.
- Use a stable `provider_key` (e.g. lowercase, no spaces).

### 3. Add config keys
- In `config.yaml`: add the provider key to `providers.spot_priority` or `providers.dex_priority` in the desired order (first = primary).
- If the provider needs new options, add new keys under a clearly named section; do not change existing schema keys (see project rule "Do Not Touch").

### 4. Add tests (mocked HTTP)
- New or existing test file in `tests/`. Use `unittest.mock.patch` on the provider’s `requests.get` (patch at the module where `requests` is used, e.g. `crypto_analyzer.providers.cex.myprovider.requests.get`).
- Unit test: provider returns valid SpotQuote/DexSnapshot for mocked 200 response; handles 429/errors appropriately.
- Optionally: add to integration test that runs one poll cycle with temp SQLite and mocked HTTP (see `test_provider_integration.py`).

### 5. Docs snippet (optional but recommended)
- Add one short paragraph or bullet under CONTRIBUTING.md "Adding a New Provider" or README "Extending providers": name and one-line description so the new provider is discoverable.

## Checklist Before Finishing
- [ ] Implementation in cex/ or dex/ with correct Protocol and provider_name
- [ ] Registered in defaults.py
- [ ] Listed in config.yaml under providers.spot_priority or dex_priority
- [ ] Tests added with mocked HTTP; no live network
- [ ] (Optional) Docs snippet added

## Output
- **Files changed** (list)
- **Commands to run** (`python -m pytest -q`, `ruff check .`, optionally one poll cycle)
- **What to look for** (all tests pass; config loads; poll uses new provider when in priority list)
