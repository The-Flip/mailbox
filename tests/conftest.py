"""Shared test fixtures.

All HTTP is mocked at the transport boundary (``httpx.MockTransport``) so the
suite is hermetic — no network, no real API key. See ``docs/Testing.md``.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from flipmail import cli as cli_module
from flipmail.kit import KitClient

# A throwaway key generated per-run so detect-secrets never sees a literal.
TEST_KEY = secrets.token_hex(16)

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def make_client() -> Callable[..., KitClient]:
    """Return a factory that builds a KitClient wired to a mock transport.

    Pass ``sleep=spy`` to assert on retry backoff without actually waiting, and
    any other KitClient kwargs (e.g. ``max_retries``, ``backoff_base``).
    """

    def _make(handler: Handler, **kwargs: Any) -> KitClient:
        return KitClient(
            TEST_KEY,
            base_url="https://api.kit.com/v4",
            transport=httpx.MockTransport(handler),
            **kwargs,
        )

    return _make


@pytest.fixture
def patched_client(monkeypatch: pytest.MonkeyPatch) -> Callable[[Handler], None]:
    """Patch cli.KitClient so the CLI uses a mock transport with the given handler."""

    def install(handler: Handler) -> None:
        def factory(*_args: object, **_kwargs: object) -> KitClient:
            return KitClient(
                TEST_KEY,
                base_url="https://api.kit.com/v4",
                transport=httpx.MockTransport(handler),
            )

        monkeypatch.setattr(cli_module, "KitClient", factory)

    return install
