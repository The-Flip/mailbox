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
uv run python -m mailbox subscribers list --tags      # include each subscriber's tags
```

### Tags

```bash
uv run python -m mailbox tags list                    # the account's tags
uv run python -m mailbox tags create "Volunteers"     # idempotent

# Add/remove a tag, by id or email, individually or in bulk.
# TAG is a tag name (resolved for you) or a numeric tag id.
uv run python -m mailbox tags add "Volunteers" 12345 ada@flip.museum
uv run python -m mailbox tags add "Volunteers" --from-status active --dry-run
uv run python -m mailbox tags add "Volunteers" --all --dry-run         # everyone (preview)
uv run python -m mailbox tags add "Volunteers" --from-file emails.txt   # '-' = stdin
uv run python -m mailbox tags add "New Tag" 12345 --create-missing      # create then tag
uv run python -m mailbox tags remove "Volunteers" 12345
```

Mutating commands are deliberately careful: pass `--dry-run` to preview, and they
ask for confirmation unless you pass `--yes`. **Adding a tag can trigger Kit
automations and send email**, so it can't be undone — preview first. Bulk runs
loop one API call per subscriber (API keys can't use Kit's bulk endpoints), so
large batches are rate-limited to ~120/min and take a while.

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
