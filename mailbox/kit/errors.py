"""Exception hierarchy for Kit API failures.

Callers should catch these specific types rather than bare ``Exception`` so they
can react precisely (e.g. back off on a rate limit, re-auth on a 401).
"""

from __future__ import annotations


class KitAPIError(Exception):
    """Base class for all errors talking to the Kit API.

    Carries the HTTP status code (when there was a response) and the parsed
    error body, if any, so callers can inspect what Kit reported.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: object | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class KitClientError(KitAPIError):
    """A 4xx response — the request was rejected (bad input, etc.)."""


class KitAuthError(KitClientError):
    """A 401/403 — the API key or token is missing, invalid, or unauthorized."""


class KitNotFoundError(KitClientError):
    """A 404 — the requested resource does not exist."""


class KitRateLimitError(KitClientError):
    """A 429 — too many requests. ``retry_after`` is seconds to wait, if Kit said."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: object | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code, body=body)
        self.retry_after = retry_after


class KitServerError(KitAPIError):
    """A 5xx response — Kit had a problem. Generally safe to retry with backoff."""
