"""A thin, typed client for the Kit (kit.com) v4 API.

This is the single boundary between this app and Kit. It owns authentication,
the base URL, timeouts, and mapping HTTP failures to the :mod:`flipmail.kit.errors`
hierarchy. Keep transport concerns here; put mailing-list workflows and safety
checks in the modules that call this client.

See ``docs/KitAPI.md`` for the API specifics (auth, pagination, rate limits,
safety) and ``docs/Testing.md`` for how to test against a mocked transport.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from datetime import datetime
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Any

import httpx

from flipmail import config
from flipmail.kit.errors import (
    KitAPIError,
    KitAuthError,
    KitClientError,
    KitNotFoundError,
    KitRateLimitError,
    KitServerError,
)

#: Header name Kit expects for V4 API-key authentication.
API_KEY_HEADER = "X-Kit-Api-Key"


class KitClient:
    """Synchronous client for the Kit v4 API.

    Args:
        api_key: V4 API key. Defaults to ``config.KIT_API_KEY``.
        base_url: API base URL. Defaults to ``config.KIT_API_BASE_URL``.
        timeout: Per-request timeout in seconds.
        transport: Optional ``httpx`` transport — pass an
            ``httpx.MockTransport`` in tests to avoid real network calls.
        max_retries: Retries for transient failures (429 / 5xx). Defaults to
            ``config.KIT_API_MAX_RETRIES``.
        backoff_base: Base seconds for exponential backoff between retries.
            Defaults to ``config.KIT_API_BACKOFF_BASE``.
        sleep: Callable used to wait between retries. Defaults to ``time.sleep``;
            inject a spy in tests so they don't actually wait.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
        max_retries: int | None = None,
        backoff_base: float | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        key = api_key if api_key is not None else config.KIT_API_KEY
        if not key:
            raise KitAuthError(
                "No Kit API key provided. Set KIT_API_KEY in the environment "
                "or pass api_key=... explicitly."
            )

        self._client = httpx.Client(
            base_url=base_url or config.KIT_API_BASE_URL,
            headers={API_KEY_HEADER: key, "Accept": "application/json"},
            timeout=timeout if timeout is not None else config.KIT_API_TIMEOUT,
            transport=transport,
        )
        self._max_retries = max_retries if max_retries is not None else config.KIT_API_MAX_RETRIES
        self._backoff_base = (
            backoff_base if backoff_base is not None else config.KIT_API_BACKOFF_BASE
        )
        self._sleep = sleep if sleep is not None else time.sleep

    # -- context manager ---------------------------------------------------

    def __enter__(self) -> KitClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    # -- low-level request -------------------------------------------------

    def request(
        self, method: str, path: str, *, _retry: bool = True, **kwargs: Any
    ) -> dict[str, Any]:
        """Send a request and return the parsed JSON body.

        Transient failures (429 rate limits and 5xx server errors) are retried
        up to ``max_retries`` times with backoff that honors any ``Retry-After``
        header. An empty 2xx body (e.g. a 204 from DELETE) returns ``{}``.

        Pass ``_retry=False`` to disable retries — required for non-idempotent
        operations like sends, where a blind retry could double-send (see
        ``docs/KitAPI.md``). Tag operations are idempotent, so they retry safely.

        Raises a :class:`~flipmail.kit.errors.KitAPIError` subclass on a non-2xx
        response that is not retried (or once retries are exhausted).
        """
        attempt = 0
        while True:
            try:
                response = self._client.request(method, path, **kwargs)
            except httpx.HTTPError as err:  # network/timeout/transport failure
                raise KitAPIError(f"Request to Kit failed: {err}") from err

            if response.is_success:
                return response.json() if response.content else {}

            error = self._error_for(response)
            retriable = isinstance(error, KitRateLimitError | KitServerError)
            if _retry and retriable and attempt < self._max_retries:
                self._sleep(self._delay_for(error, attempt))
                attempt += 1
                continue
            raise error

    def _delay_for(self, error: KitAPIError, attempt: int) -> float:
        """Seconds to wait before the next retry.

        Honors a ``Retry-After`` from a rate-limit response; otherwise uses
        exponential backoff (``backoff_base * 2**attempt``).
        """
        if isinstance(error, KitRateLimitError) and error.retry_after is not None:
            return error.retry_after
        return self._backoff_base * (2**attempt)

    def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """GET ``path`` and return the parsed JSON body."""
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """POST to ``path`` and return the parsed JSON body."""
        return self.request("POST", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """DELETE ``path``; returns ``{}`` for a 204 No Content response."""
        return self.request("DELETE", path, **kwargs)

    # -- pagination --------------------------------------------------------

    def _iter_paginated(
        self,
        path: str,
        item_key: str,
        *,
        per_page: int | None = None,
        **params: Any,
    ) -> Iterator[dict[str, Any]]:
        """Yield every item from a cursor-paginated list endpoint.

        ``item_key`` is the response key holding the page's items (e.g.
        ``"subscribers"`` or ``"tags"``). ``None``-valued params are dropped.
        Walks ``pagination.end_cursor`` until ``has_next_page`` is false.
        """
        query: dict[str, Any] = {k: v for k, v in params.items() if v is not None}
        if per_page is not None:
            query["per_page"] = per_page

        after: str | None = None
        while True:
            page = dict(query)
            if after is not None:
                page["after"] = after
            body = self.get(path, params=page)
            yield from body.get(item_key, [])

            pagination = body.get("pagination") or {}
            if not pagination.get("has_next_page"):
                return
            after = pagination.get("end_cursor")
            if not after:  # defensive: no cursor means we can't advance
                return

    # -- subscribers -------------------------------------------------------

    def get_subscriber(self, subscriber_id: int) -> dict[str, Any]:
        """Fetch a single subscriber by id.

        Returns the ``subscriber`` object from Kit's response.
        """
        body = self.get(f"/subscribers/{subscriber_id}")
        return body["subscriber"]

    def list_subscribers(
        self,
        *,
        per_page: int | None = None,
        status: str | None = None,
        after: str | None = None,
        include: str | None = None,
        **params: Any,
    ) -> dict[str, Any]:
        """Fetch one page of subscribers.

        Returns the raw body: ``{"subscribers": [...], "pagination": {...}}``.
        ``per_page`` maxes out at 1000 (Kit's default is 500). Pass ``after``
        with a page's ``pagination.end_cursor`` to get the next page, or use
        :meth:`iter_subscribers` to walk every page automatically. Pass
        ``include="tags"`` to embed each subscriber's tags in the response.
        """
        query: dict[str, Any] = dict(params)
        if per_page is not None:
            query["per_page"] = per_page
        if status is not None:
            query["status"] = status
        if after is not None:
            query["after"] = after
        if include is not None:
            query["include"] = include
        return self.get("/subscribers", params=query)

    def iter_subscribers(
        self,
        *,
        per_page: int | None = None,
        status: str | None = None,
        include: str | None = None,
        **params: Any,
    ) -> Iterator[dict[str, Any]]:
        """Yield every subscriber, transparently following cursor pagination.

        Pass ``include="tags"`` to embed each subscriber's tags.
        """
        return self._iter_paginated(
            "/subscribers",
            "subscribers",
            per_page=per_page,
            status=status,
            include=include,
            **params,
        )

    # -- tags --------------------------------------------------------------

    def list_tags(
        self,
        *,
        per_page: int | None = None,
        after: str | None = None,
        **params: Any,
    ) -> dict[str, Any]:
        """Fetch one page of the account's tags.

        Returns the raw body: ``{"tags": [...], "pagination": {...}}``.
        """
        query: dict[str, Any] = dict(params)
        if per_page is not None:
            query["per_page"] = per_page
        if after is not None:
            query["after"] = after
        return self.get("/tags", params=query)

    def iter_tags(self, *, per_page: int | None = None, **params: Any) -> Iterator[dict[str, Any]]:
        """Yield every tag in the account, following cursor pagination."""
        return self._iter_paginated("/tags", "tags", per_page=per_page, **params)

    def iter_subscriber_tags(
        self, subscriber_id: int, *, per_page: int | None = None
    ) -> Iterator[dict[str, Any]]:
        """Yield every tag applied to a single subscriber."""
        return self._iter_paginated(f"/subscribers/{subscriber_id}/tags", "tags", per_page=per_page)

    def iter_tag_subscribers(
        self, tag_id: int, *, status: str | None = None, per_page: int | None = None
    ) -> Iterator[dict[str, Any]]:
        """Yield the subscribers who currently have ``tag_id``.

        ``status`` filters by subscriber state; pass ``"all"`` for every state
        (Kit's endpoint defaults to ``active`` only). Lets a caller act on just
        the tag's holders instead of scanning every subscriber.
        """
        return self._iter_paginated(
            f"/tags/{tag_id}/subscribers", "subscribers", status=status, per_page=per_page
        )

    def create_tag(self, name: str) -> dict[str, Any]:
        """Create a tag (idempotent — returns the existing tag if the name exists).

        Returns the ``tag`` object (``{"id": ..., "name": ...}``).
        """
        return self.post("/tags", json={"name": name})["tag"]

    def add_tag(
        self,
        tag_id: int,
        *,
        subscriber_id: int | None = None,
        email: str | None = None,
    ) -> dict[str, Any]:
        """Apply a tag to a subscriber, addressed by id or email.

        Idempotent: re-tagging an already-tagged subscriber succeeds (Kit
        returns 200 instead of 201). Returns the ``subscriber`` object.
        """
        if subscriber_id is not None:
            body = self.post(f"/tags/{tag_id}/subscribers/{subscriber_id}")
        elif email is not None:
            body = self.post(f"/tags/{tag_id}/subscribers", json={"email_address": email})
        else:
            raise ValueError("add_tag requires subscriber_id or email")
        return body.get("subscriber", {})

    def remove_tag(
        self,
        tag_id: int,
        *,
        subscriber_id: int | None = None,
        email: str | None = None,
    ) -> None:
        """Remove a tag from a subscriber, addressed by id or email."""
        if subscriber_id is not None:
            self.delete(f"/tags/{tag_id}/subscribers/{subscriber_id}")
        elif email is not None:
            self.delete(f"/tags/{tag_id}/subscribers", json={"email_address": email})
        else:
            raise ValueError("remove_tag requires subscriber_id or email")

    # -- error mapping -----------------------------------------------------

    @staticmethod
    def _error_for(response: httpx.Response) -> KitAPIError:
        """Translate a non-2xx response into the right exception type."""
        status = response.status_code
        try:
            body: object | None = response.json()
        except ValueError:
            body = response.text or None

        message = f"Kit API returned {status} for {response.request.url}"

        if status == 429:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            return KitRateLimitError(
                message, status_code=status, body=body, retry_after=retry_after
            )
        if status in (401, 403):
            return KitAuthError(message, status_code=status, body=body)
        if status == 404:
            return KitNotFoundError(message, status_code=status, body=body)
        if 400 <= status < 500:
            return KitClientError(message, status_code=status, body=body)
        return KitServerError(message, status_code=status, body=body)


def _parse_retry_after(header: str | None) -> float | None:
    """Parse a ``Retry-After`` header into seconds to wait.

    The HTTP spec allows either a number of seconds or an HTTP date. Returns
    ``None`` if the header is absent or unparseable.
    """
    if not header:
        return None
    try:
        return float(header)
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(header)
    except TypeError, ValueError:
        return None
    delta = (retry_at - datetime.now(retry_at.tzinfo)).total_seconds()
    return max(0.0, delta)
