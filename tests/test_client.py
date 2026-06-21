"""Tests for KitClient.

All HTTP is mocked at the transport boundary (``httpx.MockTransport``) so the
suite is hermetic — no network, no real API key. See ``docs/Testing.md``.
"""

from __future__ import annotations

import secrets

import httpx
import pytest

from mailbox.kit import (
    KitAuthError,
    KitClient,
    KitNotFoundError,
    KitRateLimitError,
    KitServerError,
)

# A throwaway key generated per-run so detect-secrets never sees a literal.
TEST_KEY = secrets.token_hex(16)


def make_client(handler: httpx.MockTransport | object) -> KitClient:
    """Build a KitClient wired to a mock transport handler."""
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return KitClient(TEST_KEY, base_url="https://api.kit.com/v4", transport=transport)


def test_requires_an_api_key():
    """Constructing without any key fails fast rather than making bad calls."""
    with pytest.raises(KitAuthError):
        KitClient("")


def test_get_subscriber_sends_auth_header_and_unwraps_body():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Kit-Api-Key"] == TEST_KEY
        assert request.url.path == "/v4/subscribers/42"
        return httpx.Response(200, json={"subscriber": {"id": 42, "email": "a@b.co"}})

    with make_client(handler) as client:
        subscriber = client.get_subscriber(42)

    assert subscriber == {"id": 42, "email": "a@b.co"}


def test_404_maps_to_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"errors": ["not found"]})

    with make_client(handler) as client, pytest.raises(KitNotFoundError) as exc:
        client.get_subscriber(999)

    assert exc.value.status_code == 404


def test_429_maps_to_rate_limit_with_retry_after():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "30"}, json={})

    with make_client(handler) as client, pytest.raises(KitRateLimitError) as exc:
        client.get("/subscribers")

    assert exc.value.retry_after == 30.0


def test_5xx_maps_to_server_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")

    with make_client(handler) as client, pytest.raises(KitServerError):
        client.get("/subscribers")


def test_list_subscribers_passes_query_params():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v4/subscribers"
        assert request.url.params["per_page"] == "2"
        assert request.url.params["status"] == "active"
        return httpx.Response(200, json={"subscribers": [], "pagination": {}})

    with make_client(handler) as client:
        client.list_subscribers(per_page=2, status="active")


def test_iter_subscribers_follows_cursor_pagination():
    """The iterator should walk every page via end_cursor and stop cleanly."""

    def handler(request: httpx.Request) -> httpx.Response:
        after = request.url.params.get("after")
        if after is None:
            return httpx.Response(
                200,
                json={
                    "subscribers": [{"id": 1}, {"id": 2}],
                    "pagination": {"has_next_page": True, "end_cursor": "CUR2"},
                },
            )
        assert after == "CUR2"
        return httpx.Response(
            200,
            json={
                "subscribers": [{"id": 3}],
                "pagination": {"has_next_page": False, "end_cursor": None},
            },
        )

    with make_client(handler) as client:
        ids = [s["id"] for s in client.iter_subscribers(per_page=2)]

    assert ids == [1, 2, 3]
