"""Client for the Kit (kit.com) v4 API.

All HTTP access to Kit goes through this package — see :class:`flipmail.kit.client.KitClient`.
"""

from flipmail.kit.client import KitClient
from flipmail.kit.errors import (
    KitAPIError,
    KitAuthError,
    KitClientError,
    KitNotFoundError,
    KitRateLimitError,
    KitServerError,
)

__all__ = [
    "KitAPIError",
    "KitAuthError",
    "KitClient",
    "KitClientError",
    "KitNotFoundError",
    "KitRateLimitError",
    "KitServerError",
]
