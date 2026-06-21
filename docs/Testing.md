# Testing

Tests use [`pytest`](https://docs.pytest.org/). Run the fast suite with `make test`.

## Golden rule: don't hit the live Kit API by default

The default suite must be hermetic — no network, no real `KIT_API_KEY`. Mock HTTP at the transport boundary so tests are fast, deterministic, and safe (a test must never send a real broadcast).

Two good approaches:

1. **`httpx.MockTransport`** — construct the `httpx.Client` (and thus `KitClient`) with a mock transport that returns canned responses. This exercises real request building, URL joining, header logic, and response parsing.

   ```python
   import httpx
   from mailbox.kit.client import KitClient

   def test_get_subscriber():
       def handler(request: httpx.Request) -> httpx.Response:
           assert request.headers["X-Kit-Api-Key"] == "test-key"
           assert request.url.path == "/v4/subscribers/42"
           return httpx.Response(200, json={"subscriber": {"id": 42}})

       client = KitClient(api_key="test-key", transport=httpx.MockTransport(handler))
       assert client.get_subscriber(42)["id"] == 42
   ```

2. **`respx`** (add with `uv add --dev respx`) if you prefer a declarative routing API. Either is fine; `MockTransport` needs no extra dependency.

Avoid `unittest.mock.patch` on `httpx` internals — it couples tests to implementation details. Mock at the transport, not the method.

## Test organization

- Tests live in `tests/` and mirror the package: `mailbox/kit/client.py` → `tests/test_client.py`.
- Name tests descriptively (`test_list_subscribers_follows_pagination`), and give non-obvious ones a one-line docstring explaining what behavior they pin down.
- Put shared fixtures in `tests/conftest.py`.
- Generate any secrets/tokens dynamically (`secrets.token_hex(16)`) — never commit a literal that `detect-secrets` would flag.

## Integration tests (live API)

Tests that genuinely need the live Kit API must be marked:

```python
import pytest

@pytest.mark.integration
def test_against_live_kit():
    ...
```

- `make test` runs `pytest -m "not integration"` and **excludes** these.
- `make test-all` runs everything and requires a real `KIT_API_KEY` in the environment plus network access.
- Integration tests must never send to a real audience or mutate production data. Use a dedicated test account/segment, and prefer read-only checks.

## What to test

- Request construction: correct URL, method, auth header, query params, body.
- Response parsing and the typed return shape.
- Error mapping: a `429`/`4xx`/`5xx` becomes the right `KitAPIError` subclass.
- Retry/backoff behavior for transient errors.
- Pagination: that a multi-page list is fully and correctly assembled.
- Safety rails on send/mutation workflows (dry-run, idempotency, confirmation).

## TDD

- Fixing a bug: write a failing test that reproduces it first, then fix the code.
- New behavior: include tests; consider writing them first.
