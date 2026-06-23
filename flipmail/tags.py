"""Tag workflows: resolving tag names, selecting subscribers, and applying tags.

This is the workflow layer above :class:`flipmail.kit.client.KitClient` (which is
pure HTTP transport). It holds the business logic and the safety-relevant
accounting for tag operations.

**Bulk note.** Kit's true bulk endpoints (``/v4/bulk/*``) require OAuth and
reject API-key auth, which is what this project uses. So :func:`apply_tag`
implements "bulk" by *looping* the per-subscriber endpoints; the client handles
rate-limit backoff. :func:`apply_tag` is the single entry point the CLI calls and
returns a :class:`BulkResult` shaped like Kit's own bulk response — so a future
OAuth-backed bulk implementation can replace just this function without changing
the CLI.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from flipmail.kit import KitAPIError, KitClient

TagAction = Literal["add", "remove"]


class TagResolutionError(Exception):
    """A tag name could not be resolved to a single tag (missing or ambiguous)."""


def resolve_tag(client: KitClient, ref: str, *, create_missing: bool = False) -> dict[str, object]:
    """Resolve a tag reference to a tag object (``{"id": ..., "name": ...}``).

    ``ref`` may be a numeric tag id (used as-is, no lookup) or a tag name matched
    case-insensitively against the account's tags.

    Raises :class:`TagResolutionError` if the name matches no tag (unless
    ``create_missing`` is set, in which case the tag is created) or if it matches
    more than one tag (Kit permits duplicate names).
    """
    if ref.isdigit():
        return {"id": int(ref), "name": None}

    matches = [tag for tag in client.iter_tags() if str(tag.get("name", "")).lower() == ref.lower()]

    if not matches:
        if create_missing:
            return client.create_tag(ref)
        raise TagResolutionError(
            f"No tag named {ref!r}. Create it first (`tags create {ref!r}`) "
            f"or pass --create-missing."
        )
    if len(matches) > 1:
        ids = ", ".join(str(tag.get("id")) for tag in matches)
        raise TagResolutionError(
            f"Tag name {ref!r} is ambiguous: ids {ids}. Pass the numeric id instead."
        )
    return matches[0]


@dataclass(frozen=True)
class Target:
    """A subscriber to act on, addressed by id or email, with a display label."""

    subscriber_id: int | None = None
    email: str | None = None

    @property
    def label(self) -> str:
        if self.email is not None:
            return self.email
        return f"#{self.subscriber_id}"

    @property
    def key(self) -> tuple[str, object]:
        """A hashable identity used to dedupe targets."""
        if self.subscriber_id is not None:
            return ("id", self.subscriber_id)
        return ("email", self.email)


def parse_target(token: str) -> Target:
    """Parse a single CLI token into a :class:`Target` (email if it has ``@``)."""
    token = token.strip()
    if "@" in token:
        return Target(email=token)
    if token.isdigit():
        return Target(subscriber_id=int(token))
    raise ValueError(f"{token!r} is neither a subscriber id nor an email address")


def collect_targets(
    client: KitClient,
    *,
    tokens: Sequence[str] = (),
    from_status: str | None = None,
    all_subscribers: bool = False,
    limit: int | None = None,
    within_tag_id: int | None = None,
) -> list[Target]:
    """Gather and de-duplicate the subscribers to act on.

    ``tokens`` are positional ids/emails. ``from_status`` / ``all_subscribers``
    pull a segment (id-addressed). ``limit`` caps a segment pull.

    ``within_tag_id`` scopes the segment to subscribers who already hold that
    tag, via ``GET /tags/{id}/subscribers`` — used by ``remove`` so a segment
    only touches the tag's holders instead of every subscriber in the account.
    Positional ``tokens`` are always honored as given, tag membership aside.
    """
    targets: list[Target] = [parse_target(token) for token in tokens]

    if all_subscribers or from_status is not None:
        if within_tag_id is not None:
            # Only subscribers who have the tag. "all" overrides Kit's
            # active-only default so we reach holders in every state.
            source = client.iter_tag_subscribers(
                within_tag_id,
                status=from_status if from_status is not None else "all",
                per_page=1000,
            )
        else:
            status = from_status if not all_subscribers else None
            source = client.iter_subscribers(status=status, per_page=1000)
        for count, subscriber in enumerate(source, start=1):
            targets.append(Target(subscriber_id=int(subscriber["id"])))
            if limit is not None and count >= limit:
                break

    # Dedupe while preserving order.
    seen: set[tuple[str, object]] = set()
    deduped: list[Target] = []
    for target in targets:
        if target.key not in seen:
            seen.add(target.key)
            deduped.append(target)
    return deduped


@dataclass
class ItemResult:
    """The outcome of applying a tag to a single target."""

    target: Target
    ok: bool
    detail: str


@dataclass
class BulkResult:
    """Accumulated outcomes of a tag operation across many targets."""

    successes: list[ItemResult] = field(default_factory=list)
    failures: list[ItemResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.successes) + len(self.failures)


def apply_tag(
    client: KitClient,
    tag_id: int,
    targets: Iterable[Target],
    *,
    action: TagAction,
) -> BulkResult:
    """Add or remove ``tag_id`` across ``targets``, one call per subscriber.

    A failure on one target (e.g. an unknown email) is recorded and the loop
    continues — one bad target never aborts the batch. The client's built-in
    backoff handles rate limits. Returns a :class:`BulkResult` summarizing every
    target's outcome.
    """
    result = BulkResult()
    for target in targets:
        try:
            if action == "add":
                client.add_tag(tag_id, subscriber_id=target.subscriber_id, email=target.email)
                result.successes.append(ItemResult(target, True, "tagged"))
            elif action == "remove":
                client.remove_tag(tag_id, subscriber_id=target.subscriber_id, email=target.email)
                result.successes.append(ItemResult(target, True, "untagged"))
            else:  # defensive: never silently fall through to a destructive default
                raise ValueError(f"Unsupported tag action {action!r}; expected 'add' or 'remove'.")
        except KitAPIError as err:
            result.failures.append(ItemResult(target, False, str(err)))
    return result
