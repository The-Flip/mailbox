"""Client for the Kit (kit.com) v4 API.

All HTTP access to Kit goes through this package — see :class:`mailbox.kit.client.KitClient`.
"""

from mailbox.kit.client import KitClient
from mailbox.kit.errors import (
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
