"""A thin, typed client for the Kit (kit.com) v4 API.

This is the single boundary between this app and Kit. It owns authentication,
the base URL, timeouts, and mapping HTTP failures to the :mod:`mailbox.kit.errors`
hierarchy. Keep transport concerns here; put mailing-list workflows and safety
checks in the modules that call this client.

See ``docs/KitAPI.md`` for the API specifics (auth, pagination, rate limits,
safety) and ``docs/Testing.md`` for how to test against a mocked transport.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

import httpx

from mailbox import config
from mailbox.kit.errors import (
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
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
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

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Send a request and return the parsed JSON body.

        Raises a :class:`~mailbox.kit.errors.KitAPIError` subclass on any
        non-2xx response.
        """
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as err:  # network/timeout/transport failure
            raise KitAPIError(f"Request to Kit failed: {err}") from err

        if response.is_success:
            if not response.content:
                return {}
            return response.json()

        raise self._error_for(response)

    def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """GET ``path`` and return the parsed JSON body."""
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """POST to ``path`` and return the parsed JSON body."""
        return self.request("POST", path, **kwargs)

    # -- example resource method -------------------------------------------

    def get_subscriber(self, subscriber_id: int) -> dict[str, Any]:
        """Fetch a single subscriber by id.

        Returns the ``subscriber`` object from Kit's response. Add sibling
        methods (``list_subscribers``, ``add_tag``, ...) following this shape
        as the project grows — see ``docs/KitAPI.md``.
        """
        body = self.get(f"/subscribers/{subscriber_id}")
        return body["subscriber"]

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
            retry_after_header = response.headers.get("Retry-After")
            retry_after = float(retry_after_header) if retry_after_header else None
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
