"""Configuration and secrets, read from the environment.

This module is the *only* place that reads environment variables. Everything
else imports the typed values from here. Values come from the process
environment or a local ``.env`` file (see ``.env.example``), via
``python-decouple``.
"""

from __future__ import annotations

from decouple import config

# --- Kit (kit.com) v4 API ---

#: V4 API key, sent as the ``X-Kit-Api-Key`` header. Required for real use;
#: empty by default so importing this module never fails (e.g. in unit tests
#: that construct a client with an explicit key).
KIT_API_KEY: str = config("KIT_API_KEY", default="")

#: Base URL for the Kit v4 API. Override only to point at a mock server.
KIT_API_BASE_URL: str = config("KIT_API_BASE_URL", default="https://api.kit.com/v4")

#: Per-request timeout, in seconds.
KIT_API_TIMEOUT: float = config("KIT_API_TIMEOUT", default=30, cast=float)

#: How many times to retry transient failures (429 / 5xx) before giving up.
KIT_API_MAX_RETRIES: int = config("KIT_API_MAX_RETRIES", default=3, cast=int)

#: Base delay (seconds) for exponential backoff between retries. The nth retry
#: waits ``KIT_API_BACKOFF_BASE * 2**n`` seconds, unless the response carried a
#: ``Retry-After`` header (which takes precedence).
KIT_API_BACKOFF_BASE: float = config("KIT_API_BACKOFF_BASE", default=0.5, cast=float)
