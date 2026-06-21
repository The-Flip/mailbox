"""Command-line interface for Mailbox.

Run it with::

    uv run python -m mailbox --help

Commands are read-only for now. Anything that sends mail or mutates subscribers
must follow the safety rules in ``docs/KitAPI.md`` (dry-run, confirmation).
"""

from __future__ import annotations

import sys

import click

from mailbox import __version__
from mailbox.kit import KitAPIError, KitClient


@click.group()
@click.version_option(__version__, prog_name="mailbox")
def cli() -> None:
    """Manage The Flip's mailing lists via the Kit (kit.com) API."""


@cli.group()
def subscribers() -> None:
    """Inspect subscribers."""


@subscribers.command(name="list")
@click.option(
    "--status",
    type=click.Choice(["active", "inactive", "bounced", "cancelled", "complained"]),
    help="Only show subscribers in this state.",
)
@click.option(
    "--limit",
    type=click.IntRange(min=1),
    default=20,
    show_default=True,
    help="Maximum subscribers to show. Use --all to fetch everyone.",
)
@click.option("--all", "fetch_all", is_flag=True, help="Fetch every subscriber (ignores --limit).")
def list_subscribers(status: str | None, limit: int, fetch_all: bool) -> None:
    """List subscribers as a simple table."""
    try:
        with KitClient() as client:
            rows = _collect(client, status=status, limit=None if fetch_all else limit)
    except KitAPIError as err:
        raise click.ClickException(f"Kit API error: {err}") from err

    if not rows:
        click.echo("No subscribers found.")
        return

    _print_table(rows)
    click.echo(f"\n{len(rows)} subscriber(s).")


def _collect(
    client: KitClient, *, status: str | None, limit: int | None
) -> list[dict[str, object]]:
    """Pull subscribers, stopping at ``limit`` unless it is None (= all)."""
    # Ask Kit for at most as many as we need per page (cap at its 1000 max).
    per_page = None if limit is None else min(limit, 1000)
    collected: list[dict[str, object]] = []
    for subscriber in client.iter_subscribers(status=status, per_page=per_page):
        collected.append(subscriber)
        if limit is not None and len(collected) >= limit:
            break
    return collected


def _print_table(rows: list[dict[str, object]]) -> None:
    """Print id / email / name / state aligned to the widest column."""
    headers = ("ID", "EMAIL", "NAME", "STATE")
    table = [
        (
            str(r.get("id", "")),
            str(r.get("email_address", "")),
            str(r.get("first_name") or ""),
            str(r.get("state", "")),
        )
        for r in rows
    ]
    widths = [max(len(headers[i]), *(len(row[i]) for row in table)) for i in range(len(headers))]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    click.echo(fmt.format(*headers))
    for row in table:
        click.echo(fmt.format(*row))


def main() -> None:
    """Entry point used by ``python -m mailbox``."""
    cli()


if __name__ == "__main__":
    sys.exit(cli())
