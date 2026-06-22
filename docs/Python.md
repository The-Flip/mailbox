# Python Conventions

Coding rules for this project. These complement the always-loaded rules in [`CLAUDE.md`](../CLAUDE.md).

## Environment & dependencies

- **`uv` manages everything.** Python 3.14, the venv, and dependencies are all managed by [`uv`](https://docs.astral.sh/uv/). Run code and tools with `uv run ...` (the `Makefile` wraps the common ones).
- **Add dependencies with `uv`**, not by editing `pyproject.toml` by hand:
  - Runtime: `uv add <package>`
  - Dev-only: `uv add --dev <package>`
- **Always use the latest stable version.** Check PyPI before adding or bumping. Verify compatibility with existing pins; read changelogs before crossing a major version.
- Commit the lockfile (`uv.lock`) so CI and everyone else resolve to the same versions.

## Secrets & configuration

- **Never hardcode keys, tokens, or passwords.** Read them from the environment via `python-decouple`, and do it only in `flipmail/config.py`. Everything else imports from there.
- In tests, generate any needed secrets dynamically (`secrets.token_hex(16)`) so the `detect-secrets` pre-commit hook doesn't flag a committed literal.
- `.env` is git-ignored. `.env.example` documents every variable the app reads — keep it in sync when you add config.

## Typing

- Write type hints on public functions and methods. `mypy` runs in CI and as a pre-commit hook.
- Don't add `# type: ignore` to silence errors without explicit approval — fix the cause. If a third-party package lacks stubs, that's already handled globally in `pyproject.toml` (`disable_error_code = ["import-untyped", "import-not-found"]`).
- Use modern syntax: `X | None` over `Optional[X]`, builtin generics (`list[str]`), etc. (`ruff`'s `UP` rules enforce this.)

## Linting & formatting

- `ruff` is the formatter and linter. `make lint` formats and auto-fixes; CI checks formatting with `ruff format --check`.
- **Don't add `# noqa`** to silence a warning without approval. Fix the underlying issue.
- Line length target is 100; the formatter owns wrapping (`E501` is ignored).

## Error handling

- **Fail fast and loud.** Raise specific exceptions with useful messages rather than returning `None` or swallowing errors.
- For Kit API failures, raise from the `KitAPIError` hierarchy (`flipmail/kit/errors.py`) so callers can handle precisely. Never catch bare `except:` / `except Exception` to hide a problem.
- Use `raise ... from err` to preserve the cause when re-raising.

## Class design

- **Prefer mixins that call `super()`** over non-cooperative base classes — Python's MRO silently skips siblings when a base class doesn't cooperate.
- Don't create stateless classes that are just bags of `@staticmethod`s — use module-level functions.
- Keep `KitClient` focused on transport (auth, retries, pagination). Put workflow/business logic in separate modules.

## HTTP / API client

- All Kit access goes through `flipmail/kit/client.py`. See [KitAPI.md](KitAPI.md) for the API specifics (auth, pagination, rate limits, safety).
- Build in retry/backoff for transient errors (`429`, `5xx`). Don't hammer the API on failure.
- Prefer small, explicit methods over a generic `request()` escape hatch leaking `httpx` to callers.
