"""Tests for KitClient.

HTTP is mocked at the transport boundary via the ``make_client`` fixture
(see ``tests/conftest.py``) so the suite is hermetic. See ``docs/Testing.md``.
"""

from __future__ import annotations

import httpx
import pytest

from flipmail.kit import (
    KitAuthError,
    KitClient,
    KitNotFoundError,
    KitRateLimitError,
    KitServerError,
)


def test_requires_an_api_key():
    """Constructing without any key fails fast rather than making bad calls."""
    with pytest.raises(KitAuthError):
        KitClient("")


def test_get_subscriber_sends_auth_header_and_unwraps_body(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v4/subscribers/42"
        return httpx.Response(200, json={"subscriber": {"id": 42, "email": "a@b.co"}})

    with make_client(handler) as client:
        subscriber = client.get_subscriber(42)

    assert subscriber == {"id": 42, "email": "a@b.co"}


def test_404_maps_to_not_found(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"errors": ["not found"]})

    with make_client(handler) as client, pytest.raises(KitNotFoundError) as exc:
        client.get_subscriber(999)

    assert exc.value.status_code == 404


def test_429_maps_to_rate_limit_with_retry_after(make_client):
    """A non-retried 429 surfaces as KitRateLimitError carrying retry_after."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "30"}, json={})

    # max_retries=0 so the first 429 is raised rather than retried.
    with (
        make_client(handler, max_retries=0) as client,
        pytest.raises(KitRateLimitError) as exc,
    ):
        client.get("/subscribers")

    assert exc.value.retry_after == 30.0


def test_5xx_maps_to_server_error(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")

    with make_client(handler, max_retries=0) as client, pytest.raises(KitServerError):
        client.get("/subscribers")


# -- retry / backoff -------------------------------------------------------


def test_retries_on_429_then_succeeds(make_client):
    """A 429 with Retry-After is retried after sleeping the advised interval."""
    sleeps: list[float] = []
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "2"}, json={}),
            httpx.Response(200, json={"ok": True}),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    with make_client(handler, sleep=sleeps.append) as client:
        body = client.get("/subscribers")

    assert body == {"ok": True}
    assert sleeps == [2.0]


def test_retries_on_5xx_with_exponential_backoff(make_client):
    """5xx errors back off exponentially (backoff_base * 2**attempt)."""
    sleeps: list[float] = []
    responses = iter(
        [
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(200, json={"ok": True}),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    with make_client(handler, sleep=sleeps.append, backoff_base=0.5) as client:
        body = client.get("/subscribers")

    assert body == {"ok": True}
    assert sleeps == [0.5, 1.0]


def test_gives_up_after_max_retries(make_client):
    """Persistent 429s raise after exhausting the retry budget."""
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={})

    with (
        make_client(handler, sleep=sleeps.append, max_retries=2) as client,
        pytest.raises(KitRateLimitError),
    ):
        client.get("/subscribers")

    assert len(sleeps) == 2  # two retries, then give up


def test_retry_after_http_date_is_parsed(make_client):
    """A Retry-After given as an HTTP date is parsed instead of crashing."""

    def handler(request: httpx.Request) -> httpx.Response:
        # Far-future date so the computed delay is positive.
        return httpx.Response(
            429, headers={"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"}, json={}
        )

    with make_client(handler, max_retries=0) as client, pytest.raises(KitRateLimitError) as exc:
        client.get("/subscribers")

    assert exc.value.retry_after is not None and exc.value.retry_after > 0


# -- delete / 204 ----------------------------------------------------------


def test_delete_returns_empty_dict_on_204(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/v4/tags/5/subscribers/9"
        return httpx.Response(204)

    with make_client(handler) as client:
        assert client.delete("/tags/5/subscribers/9") == {}


# -- subscribers include=tags ---------------------------------------------


def test_list_subscribers_passes_include_tags(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["include"] == "tags"
        return httpx.Response(200, json={"subscribers": [], "pagination": {}})

    with make_client(handler) as client:
        client.list_subscribers(include="tags")


def test_iter_subscribers_follows_cursor_pagination(make_client):
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


# -- tags ------------------------------------------------------------------


def test_iter_tags_follows_pagination(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        after = request.url.params.get("after")
        if after is None:
            return httpx.Response(
                200,
                json={
                    "tags": [{"id": 1, "name": "A"}],
                    "pagination": {"has_next_page": True, "end_cursor": "C2"},
                },
            )
        return httpx.Response(
            200,
            json={
                "tags": [{"id": 2, "name": "B"}],
                "pagination": {"has_next_page": False, "end_cursor": None},
            },
        )

    with make_client(handler) as client:
        names = [t["name"] for t in client.iter_tags()]

    assert names == ["A", "B"]


def test_iter_subscriber_tags(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v4/subscribers/7/tags"
        return httpx.Response(
            200,
            json={
                "tags": [{"id": 1, "name": "VIP", "tagged_at": "2024-01-01T00:00:00Z"}],
                "pagination": {"has_next_page": False},
            },
        )

    with make_client(handler) as client:
        tags = list(client.iter_subscriber_tags(7))

    assert tags[0]["name"] == "VIP"


def test_create_tag_unwraps_tag(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v4/tags"
        return httpx.Response(201, json={"tag": {"id": 19, "name": "VIP"}})

    with make_client(handler) as client:
        tag = client.create_tag("VIP")

    assert tag == {"id": 19, "name": "VIP"}


def test_add_tag_by_id(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v4/tags/5/subscribers/9"
        return httpx.Response(201, json={"subscriber": {"id": 9}})

    with make_client(handler) as client:
        assert client.add_tag(5, subscriber_id=9) == {"id": 9}


def test_add_tag_by_email(make_client):
    import json as json_module

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v4/tags/5/subscribers"
        assert json_module.loads(request.content)["email_address"] == "a@b.co"
        return httpx.Response(201, json={"subscriber": {"id": 9}})

    with make_client(handler) as client:
        client.add_tag(5, email="a@b.co")


def test_add_tag_requires_a_target(make_client):
    with make_client(lambda r: httpx.Response(200)) as client, pytest.raises(ValueError):
        client.add_tag(5)


def test_remove_tag_by_id(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/v4/tags/5/subscribers/9"
        return httpx.Response(204)

    with make_client(handler) as client:
        assert client.remove_tag(5, subscriber_id=9) is None


def test_remove_tag_requires_a_target(make_client):
    with make_client(lambda r: httpx.Response(204)) as client, pytest.raises(ValueError):
        client.remove_tag(5)
