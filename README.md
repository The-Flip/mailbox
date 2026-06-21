# Mailbox — The Flip's Mailing-List Management

Mailbox manages mailing lists and related information for [The Flip](https://www.theflip.museum/) pinball museum. It is a Python application built on the [Kit (kit.com) v4 API](https://developers.kit.com/), where mailing lists, subscribers, tags, sequences, and broadcasts are composed and sent.

It is a sibling of [`flipfix`](../flipfix) (the museum's maintenance-tracking app) and deliberately mirrors its tooling and conventions.

## Requirements

- Python 3.14+
- [`uv`](https://docs.astral.sh/uv/) for dependency and environment management

## Setup

```bash
make bootstrap
```

This syncs dependencies with `uv`, installs pre-commit hooks, and creates `.env` from `.env.example`. Then add your Kit API key to `.env`:

```bash
# .env
KIT_API_KEY=your-v4-api-key
```

Create a V4 API key in your Kit account under **Settings → Developer**. See [docs/KitAPI.md](docs/KitAPI.md).

## Common commands

```bash
make test        # Fast test suite (no live API calls)
make quality     # Format, lint, typecheck
make test-all    # Full suite including @integration tests (needs a real key + network)
```

## CLI

Mailbox ships a small command-line interface (read-only for now). Run it with
`uv run python -m mailbox`:

```bash
uv run python -m mailbox --help
uv run python -m mailbox subscribers list             # first 20 subscribers
uv run python -m mailbox subscribers list --status active --limit 50
uv run python -m mailbox subscribers list --all       # walk every page
```

Example output:

```text
ID          EMAIL                 NAME   STATE
4163290803  ada@example.com       Ada    active
4163249277  grace@example.com     Grace  active

2 subscriber(s).
```

You can also drive the client library directly:

```bash
uv run python -c "from mailbox.kit import KitClient; print(KitClient().get_subscriber(1))"
```

## Documentation

Developer documentation lives in [docs/](docs/README.md). Start with [docs/KitAPI.md](docs/KitAPI.md) before writing any code that touches Kit.

> **Sending email is hard to undo.** Operations that send mail or mutate
> subscribers must be deliberate, idempotent, and dry-run-able. See the safety
> section in [docs/KitAPI.md](docs/KitAPI.md#safety).
