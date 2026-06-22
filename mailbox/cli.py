"""Command-line interface for Mailbox.

Run it with::

    uv run python -m mailbox --help

Read commands (``subscribers list``, ``tags list``) are always safe. Mutating
commands (``tags add`` / ``tags remove``) follow the safety rules in
``docs/KitAPI.md``: they support ``--dry-run`` and require confirmation unless
``--yes`` is given, because tagging can trigger Kit automations and send email.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

import click

from mailbox import __version__
from mailbox import tags as tags_workflow
from mailbox.kit import KitAPIError, KitClient
from mailbox.tags import TagResolutionError

#: Subscriber states Kit recognizes, used by --status options.
SUBSCRIBER_STATES = ["active", "inactive", "bounced", "cancelled", "complained"]


@click.group()
@click.version_option(__version__, prog_name="mailbox")
def cli() -> None:
    """Manage The Flip's mailing lists via the Kit (kit.com) API."""


# --------------------------------------------------------------------------- #
# subscribers
# --------------------------------------------------------------------------- #


@cli.group()
def subscribers() -> None:
    """Inspect subscribers."""


@subscribers.command(name="list")
@click.option(
    "--status",
    type=click.Choice(SUBSCRIBER_STATES),
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
@click.option("--tags", "show_tags", is_flag=True, help="Include each subscriber's tags.")
def list_subscribers(status: str | None, limit: int, fetch_all: bool, show_tags: bool) -> None:
    """List subscribers as a simple table."""
    try:
        with KitClient() as client:
            rows = _collect(
                client,
                status=status,
                limit=None if fetch_all else limit,
                include="tags" if show_tags else None,
            )
    except KitAPIError as err:
        raise click.ClickException(f"Kit API error: {err}") from err

    if not rows:
        click.echo("No subscribers found.")
        return

    headers = ["ID", "EMAIL", "NAME", "STATE"]
    if show_tags:
        headers.append("TAGS")
    table = []
    for r in rows:
        row = [
            str(r.get("id", "")),
            str(r.get("email_address", "")),
            str(r.get("first_name") or ""),
            str(r.get("state", "")),
        ]
        if show_tags:
            tag_list = r.get("tags")
            names = (
                ", ".join(str(t.get("name", "")) for t in tag_list if isinstance(t, dict))
                if isinstance(tag_list, list)
                else ""
            )
            row.append(names)
        table.append(tuple(row))

    _print_table(tuple(headers), table)
    click.echo(f"\n{len(rows)} subscriber(s).")


def _collect(
    client: KitClient, *, status: str | None, limit: int | None, include: str | None = None
) -> list[dict[str, object]]:
    """Pull subscribers, stopping at ``limit`` unless it is None (= all)."""
    # Ask Kit for at most as many as we need per page (cap at its 1000 max).
    per_page = None if limit is None else min(limit, 1000)
    collected: list[dict[str, object]] = []
    for subscriber in client.iter_subscribers(status=status, per_page=per_page, include=include):
        collected.append(subscriber)
        if limit is not None and len(collected) >= limit:
            break
    return collected


# --------------------------------------------------------------------------- #
# tags
# --------------------------------------------------------------------------- #


@cli.group()
def tags() -> None:
    """List tags and add/remove them on subscribers."""


@tags.command(name="list")
def list_tags() -> None:
    """List every tag in the account."""
    try:
        with KitClient() as client:
            rows = list(client.iter_tags())
    except KitAPIError as err:
        raise click.ClickException(f"Kit API error: {err}") from err

    if not rows:
        click.echo("No tags found.")
        return

    table = [
        (str(t.get("id", "")), str(t.get("name", "")), str(t.get("subscriber_count", "")))
        for t in rows
    ]
    _print_table(("ID", "NAME", "SUBSCRIBERS"), table)
    click.echo(f"\n{len(rows)} tag(s).")


@tags.command(name="create")
@click.argument("name")
def create_tag(name: str) -> None:
    """Create a tag (idempotent — returns the existing tag if NAME already exists)."""
    try:
        with KitClient() as client:
            tag = client.create_tag(name)
    except KitAPIError as err:
        raise click.ClickException(f"Kit API error: {err}") from err
    click.echo(f"Tag {tag.get('name')!r} (id {tag.get('id')}).")


def _selector_options(func):  # type: ignore[no-untyped-def]
    """Shared subscriber-selector + safety options for add/remove commands."""
    func = click.argument("subscribers", nargs=-1)(func)
    func = click.option(
        "--from-status",
        type=click.Choice(SUBSCRIBER_STATES),
        help="Select every subscriber in this state.",
    )(func)
    func = click.option("--all", "all_subscribers", is_flag=True, help="Select every subscriber.")(
        func
    )
    func = click.option(
        "--from-file",
        type=click.File("r"),
        help="Read subscriber ids/emails, one per line ('-' for stdin).",
    )(func)
    func = click.option(
        "--dry-run", is_flag=True, help="Show what would change without making any changes."
    )(func)
    func = click.option(
        "--yes", "-y", "assume_yes", is_flag=True, help="Skip the confirmation prompt."
    )(func)
    return func


@tags.command(name="add")
@click.argument("tag_ref", metavar="TAG")
@_selector_options
@click.option("--create-missing", is_flag=True, help="Create TAG if it doesn't exist yet.")
def add_tag_command(
    tag_ref: str,
    subscribers: tuple[str, ...],
    from_status: str | None,
    all_subscribers: bool,
    from_file: click.utils.LazyFile | None,
    dry_run: bool,
    assume_yes: bool,
    create_missing: bool,
) -> None:
    """Add TAG to the selected subscribers (by id, email, --from-status, or --all)."""
    _run_tag_mutation(
        action="add",
        tag_ref=tag_ref,
        subscribers=subscribers,
        from_status=from_status,
        all_subscribers=all_subscribers,
        from_file=from_file,
        dry_run=dry_run,
        assume_yes=assume_yes,
        create_missing=create_missing,
    )


@tags.command(name="remove")
@click.argument("tag_ref", metavar="TAG")
@_selector_options
def remove_tag_command(
    tag_ref: str,
    subscribers: tuple[str, ...],
    from_status: str | None,
    all_subscribers: bool,
    from_file: click.utils.LazyFile | None,
    dry_run: bool,
    assume_yes: bool,
) -> None:
    """Remove TAG from the selected subscribers (by id, email, --from-status, or --all)."""
    _run_tag_mutation(
        action="remove",
        tag_ref=tag_ref,
        subscribers=subscribers,
        from_status=from_status,
        all_subscribers=all_subscribers,
        from_file=from_file,
        dry_run=dry_run,
        assume_yes=assume_yes,
        create_missing=False,
    )


def _run_tag_mutation(
    *,
    action: tags_workflow.TagAction,
    tag_ref: str,
    subscribers: tuple[str, ...],
    from_status: str | None,
    all_subscribers: bool,
    from_file: click.utils.LazyFile | None,
    dry_run: bool,
    assume_yes: bool,
    create_missing: bool,
) -> None:
    """Shared driver for ``tags add`` / ``tags remove`` with safety rails."""
    tokens = list(subscribers) + _read_tokens(from_file)
    if not tokens and not all_subscribers and from_status is None:
        raise click.ClickException(
            "No subscribers selected. Pass ids/emails, --from-status, --all, or --from-file."
        )

    verb, prep = ("Add", "to") if action == "add" else ("Remove", "from")

    try:
        with KitClient() as client:
            try:
                targets = tags_workflow.collect_targets(
                    client,
                    tokens=tokens,
                    from_status=from_status,
                    all_subscribers=all_subscribers,
                )
            except ValueError as err:
                raise click.ClickException(str(err)) from err

            if not targets:
                click.echo("No subscribers matched. Nothing to do.")
                return

            tag = tags_workflow.resolve_tag(client, tag_ref, create_missing=create_missing)
            tag_label = tag.get("name") or f"id {tag.get('id')}"
            count = len(targets)

            if dry_run:
                click.echo(
                    f"[dry-run] Would {action} tag {tag_label!r} {prep} {count} subscriber(s):"
                )
                _echo_targets(targets)
                return

            if action == "add":
                click.echo(
                    "Warning: adding a tag can trigger Kit automations and send email. "
                    "This cannot be undone."
                )
            if not assume_yes:
                click.confirm(f"{verb} tag {tag_label!r} {prep} {count} subscriber(s)?", abort=True)

            result = tags_workflow.apply_tag(client, int(str(tag["id"])), targets, action=action)
    except TagResolutionError as err:
        raise click.ClickException(str(err)) from err
    except KitAPIError as err:
        raise click.ClickException(f"Kit API error: {err}") from err

    _report_result(result, action=action)


def _read_tokens(from_file: click.utils.LazyFile | None) -> list[str]:
    """Read non-empty, non-comment lines (ids/emails) from a file or stdin."""
    if from_file is None:
        return []
    tokens: list[str] = []
    for line in from_file:
        token = line.strip()
        if token and not token.startswith("#"):
            tokens.append(token)
    return tokens


def _echo_targets(targets: Sequence[tags_workflow.Target], cap: int = 20) -> None:
    """Print target labels, capped so a huge segment doesn't flood the terminal."""
    for target in targets[:cap]:
        click.echo(f"  - {target.label}")
    if len(targets) > cap:
        click.echo(f"  ... and {len(targets) - cap} more")


def _report_result(result: tags_workflow.BulkResult, *, action: tags_workflow.TagAction) -> None:
    """Print a summary of a bulk tag operation and exit nonzero on any failure."""
    verb = "tagged" if action == "add" else "untagged"
    click.echo(f"{len(result.successes)} {verb}, {len(result.failures)} failed.")
    if result.failures:
        click.echo("Failures:")
        for item in result.failures:
            click.echo(f"  - {item.target.label}: {item.detail}")
        raise SystemExit(1)


# --------------------------------------------------------------------------- #
# shared helpers
# --------------------------------------------------------------------------- #


def _print_table(headers: tuple[str, ...], rows: Sequence[tuple[str, ...]]) -> None:
    """Print rows aligned to the widest value in each column."""
    widths = [max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(len(headers))]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    click.echo(fmt.format(*headers))
    for row in rows:
        click.echo(fmt.format(*row))


def main() -> None:
    """Entry point used by ``python -m mailbox``."""
    cli()


if __name__ == "__main__":
    sys.exit(cli())
