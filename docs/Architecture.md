# Architecture

Mailbox is a small Python application that manages The Flip's mailing lists through the [Kit (kit.com) v4 API](https://developers.kit.com/). Kit is the system of record for subscribers, tags, sequences, and broadcasts — this app does not run its own web server or database.

## Components

- **`flipmail.config`** — Loads configuration and secrets from the environment (via `python-decouple`). The single place that knows about `KIT_API_KEY`, base URL, timeouts, etc. Nothing else reads `os.environ` directly.
- **`flipmail.kit`** — The Kit API client.
  - `client.py` — `KitClient`, a thin, typed wrapper over an `httpx.Client`. Owns auth headers, base URL, timeout, retry/backoff for transient errors, and cursor-based pagination. All Kit access goes through here.
  - `errors.py` — Exception hierarchy (`KitAPIError` and subclasses) so callers can handle failures precisely instead of catching bare `Exception`.
- **Task/command modules** (added as the project grows) — Higher-level operations that compose `KitClient` calls into mailing-list workflows (e.g. import subscribers, tag a segment, schedule a broadcast). These hold the business logic and the safety rails.

## Data flow

```text
config (env) ──▶ KitClient(httpx) ──▶ Kit v4 API (https://api.kit.com/v4)
                      ▲
        task/command modules (workflows, safety checks)
```

## Design principles

- **One boundary to the outside world.** Every HTTP call to Kit goes through `KitClient`. This keeps auth, retries, rate-limit handling, and pagination in one place and makes the rest of the code trivially testable (mock the client or its transport).
- **Typed, narrow surface.** Prefer small, explicit methods (`get_subscriber`, `list_tags`) over a single generic `request()` escape hatch. Add methods as needs arise rather than leaking `httpx` details to callers.
- **Sending is dangerous; treat it that way.** Operations that send mail or mutate subscribers should be idempotent where possible, support a dry-run, and require explicit intent. See [KitAPI.md](KitAPI.md#safety).
- **Fail fast.** Surface specific exceptions with useful context rather than returning `None` or swallowing errors.

## What this project is _not_

- Not a Django app, not a web server, not a database project. (That's `../flipfix`.)
- Not a place to store subscriber data long-term — Kit owns that.
