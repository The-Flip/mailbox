# Copilot Instructions for Mailbox

This guide enables AI coding agents to work productively in this codebase. Follow it so code, docs, and workflows align with project conventions.

## Big Picture

- **Mailbox** manages The Flip pinball museum's mailing lists via the [Kit (kit.com) v4 API](https://developers.kit.com/). Kit is the system of record — there is no local web server or database.
- **Language/runtime:** Python 3.14, managed by [`uv`](https://docs.astral.sh/uv/). Run everything via `uv run` (the `Makefile` wraps common commands).
- **Core deps:** `httpx` (HTTP), `python-decouple` (config/secrets).

## Project Structure

- `mailbox/` — the application package
  - `config.py` — the only reader of environment variables (`KIT_API_KEY`, base URL, timeouts)
  - `kit/client.py` — `KitClient`, the single boundary to the Kit API (auth, retries, pagination)
  - `kit/errors.py` — `KitAPIError` hierarchy
- `tests/` — pytest suite; HTTP is mocked at the transport boundary, no live calls by default
- `docs/` — developer docs; `AGENTS.src.md` generates `CLAUDE.md`/`AGENTS.md`
- `scripts/` — standalone dev/build scripts

## Conventions

- All Kit HTTP goes through `mailbox/kit/client.py`. Never call `httpx` elsewhere.
- All secrets/config come from `mailbox/config.py` via `python-decouple`. Never hardcode keys; keep `.env.example` in sync.
- Auth header is `X-Kit-Api-Key`. Base URL: `https://api.kit.com/v4`. Rate limit: 120 req / rolling 60s (API key).
- Raise specific `KitAPIError` subclasses; never swallow errors in a bare `except`.
- Add dependencies with `uv add` / `uv add --dev`, latest stable. Don't add `# noqa` / `# type: ignore` without approval.
- Tests mirror the package and stay hermetic; live-API tests must be `@pytest.mark.integration`.

## Email safety (critical)

Sending mail and mutating subscribers are hard to undo. Any such operation must support a dry-run, be idempotent where possible, handle `429` without double-sending, and be tested against a dedicated test segment — never a live audience.

## Quality Gates

```bash
make quality   # format + lint + typecheck
make test      # fast suite
```

`CLAUDE.md` and `AGENTS.md` are **generated** from `docs/AGENTS.src.md` — edit the source and run `make agent-docs`, never the generated files.
