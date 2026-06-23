# Kit (kit.com) v4 API

Everything this project does goes through the [Kit v4 API](https://developers.kit.com/). Kit was formerly called ConvertKit. **Always verify endpoint shapes, field names, and pagination against the live reference at <https://developers.kit.com/> before implementing** — this doc captures the stable facts and our conventions, not the full endpoint catalog.

## Base URL

```text
https://api.kit.com/v4
```

Configurable via `KIT_API_BASE_URL` (override only to point at a mock server in tests).

## Authentication

Kit v4 supports two auth methods. This project uses **API-key auth** by default.

### API key (default — personal use / account automation)

Pass the key in a request header on every call:

```text
X-Kit-Api-Key: <your key>
```

Create a V4 API key in your Kit account under **Settings → Developer**. Store it as `KIT_API_KEY` in `.env` (never hardcode it). `flipmail/config.py` is the only place that reads it.

### OAuth (only for a public integration)

If this app ever needs to act on behalf of _other_ Kit accounts, it must use OAuth 2.0 and send a bearer token:

```text
Authorization: Bearer <access token>
```

OAuth also raises the rate limit (see below). We don't need it for single-account automation.

## Rate limits

- **API key:** no more than **120 requests per rolling 60-second window** per key.
- **OAuth:** up to **600 requests per rolling 60-second window**.

Exceeding the limit returns HTTP `429`. `KitClient` should respect `Retry-After` when present and otherwise back off exponentially. Don't retry non-idempotent sends blindly — see [Safety](#safety).

## Pagination

v4 uses **cursor-based pagination** (not page numbers). List endpoints return a batch plus pagination cursors; pass a cursor to fetch the next/previous batch.

- Typical query params: `per_page` (batch size) and a cursor (`after` / `before`).
- The response includes pagination metadata with the cursor(s) and whether more pages exist.

`KitClient` should expose pagination as an iterator/generator that transparently walks all pages, so callers don't manage cursors by hand. Confirm the exact field names against the live docs when implementing — they are the source of truth.

## Key resources

The v4 API covers (non-exhaustive — check the reference):

- **Subscribers** — create, fetch, update, list, and filter the people on your lists.
- **Tags** — label subscribers; add/remove tags; list tagged subscribers.
- **Custom fields** — structured data attached to subscribers.
- **Sequences** (email courses) — enroll/list subscribers.
- **Broadcasts** — one-off emails to a segment; compose and send.
- **Forms** — subscription forms and their subscribers.
- **Bulk requests & async processing** — v4 supports bulk operations for large changes. **These require OAuth and reject API-key auth** (see below).

## Tags

Tags are how we segment subscribers. The endpoints we use (all via `KitClient`):

| Operation                  | Method & path                            | Notes                                                                                   |
| -------------------------- | ---------------------------------------- | --------------------------------------------------------------------------------------- |
| List tags                  | `GET /tags`                              | Cursor-paginated; each tag has `id`, `name`, `subscriber_count`.                        |
| List a subscriber's tags   | `GET /subscribers/{id}/tags`             | Tags include `tagged_at`.                                                               |
| List a tag's subscribers   | `GET /tags/{tag_id}/subscribers`         | Cursor-paginated; `status` defaults to `active` (pass `all` for every state).           |
| Subscribers **with** tags  | `GET /subscribers?include=tags`          | Tags inline (`id`, `name`) — one sweep, no N+1.                                         |
| Create a tag               | `POST /tags` `{"name": ...}`             | Idempotent: 200 if the name already exists.                                             |
| Add tag to subscriber      | `POST /tags/{tag_id}/subscribers/{id}`   | Or `.../subscribers` with `{"email_address": ...}`. Idempotent (200 if already tagged). |
| Remove tag from subscriber | `DELETE /tags/{tag_id}/subscribers/{id}` | Returns `204`. Email variant mirrors add.                                               |

**Adding a tag can trigger automations.** In Kit, tags commonly trigger automations/sequences that send email. Treat `add_tag` as a sending operation: dry-run first, confirm, and never tag a live segment "to test." See [Safety](#safety).

### Bulk: why we loop instead of using `/v4/bulk/*`

Kit's true bulk endpoints (`POST`/`DELETE /v4/bulk/tags/subscribers`, ≤100 taggings sync / async above) **require OAuth and reject API-key auth**. This project authenticates with an API key, so "bulk" tag operations are implemented by **looping the per-subscriber endpoints** with rate-limit backoff (see `flipmail/tags.py::apply_tag`). That keeps us within the 120 req/60s API-key limit at the cost of speed. The loop engine returns a `{successes, failures}` result shaped like Kit's bulk response, so a future OAuth-backed bulk path can replace just that function without changing the CLI.

Because looping is one call per subscriber, **scoping matters for `remove`**: a bulk untag (`--all` / `--from-status`) enumerates holders via `GET /tags/{tag_id}/subscribers` (status `all`), so it costs one DELETE per tag holder rather than one per subscriber in the account. `add --all` necessarily targets every subscriber (you're tagging people who don't have it yet), so it can't be scoped this way.

## Safety

Sending email and mutating subscribers are **hard to undo**. Treat them with care:

- **Default to dry-run.** Send/mutation workflows should support previewing what _would_ happen (which audience, how many recipients) before doing it.
- **Require explicit intent.** Don't send to a live audience as a side effect or "to test." Use a dedicated test segment.
- **Be idempotent where possible.** Guard against double-sending and double-tagging (e.g. check before create, use bulk endpoints with care, track what's already been processed).
- **Handle `429` gracefully**, but never blindly retry a send you can't prove didn't go through — you could double-send.
- **Respect consent and unsubscribes.** Never re-add or email people who have unsubscribed.

When in doubt about a send/mutation, stop and confirm with a human first.

## Errors

Map HTTP failures to the `KitAPIError` hierarchy in `flipmail/kit/errors.py` so callers can handle them precisely:

- `4xx` → client errors (bad request, auth, not found). Surface Kit's error message.
- `429` → rate-limited; carries retry timing.
- `5xx` → server errors; retryable with backoff.

Never swallow these into a bare `except`.
