"""Tests for the Click CLI.

The ``patched_client`` fixture (conftest) monkeypatches cli.KitClient to use a
mock transport, so the CLI runs end-to-end with no network or real key.
"""

from __future__ import annotations

import httpx
from click.testing import CliRunner

from flipmail import cli as cli_module

# -- subscribers list ------------------------------------------------------


def test_list_subscribers_renders_table(patched_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "subscribers": [
                    {
                        "id": 1,
                        "email_address": "ada@flip.museum",
                        "first_name": "Ada",
                        "state": "active",
                    },
                    {
                        "id": 2,
                        "email_address": "grace@flip.museum",
                        "first_name": None,
                        "state": "inactive",
                    },
                ],
                "pagination": {"has_next_page": False, "end_cursor": None},
            },
        )

    patched_client(handler)
    result = CliRunner().invoke(cli_module.cli, ["subscribers", "list"])

    assert result.exit_code == 0, result.output
    assert "ada@flip.museum" in result.output
    assert "grace@flip.museum" in result.output
    assert "2 subscriber(s)." in result.output


def test_list_subscribers_with_tags_column(patched_client):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["include"] == "tags"
        return httpx.Response(
            200,
            json={
                "subscribers": [
                    {
                        "id": 1,
                        "email_address": "ada@flip.museum",
                        "first_name": "Ada",
                        "state": "active",
                        "tags": [{"id": 1, "name": "VIP"}, {"id": 2, "name": "Volunteer"}],
                    }
                ],
                "pagination": {"has_next_page": False},
            },
        )

    patched_client(handler)
    result = CliRunner().invoke(cli_module.cli, ["subscribers", "list", "--tags"])

    assert result.exit_code == 0, result.output
    assert "TAGS" in result.output
    assert "VIP, Volunteer" in result.output


def test_limit_caps_results(patched_client):
    """--limit N stops after N rows even if more pages exist."""

    def handler(request: httpx.Request) -> httpx.Response:
        page = [
            {"id": i, "email_address": f"u{i}@flip.museum", "first_name": "U", "state": "active"}
            for i in range(50)
        ]
        return httpx.Response(
            200,
            json={"subscribers": page, "pagination": {"has_next_page": True, "end_cursor": "X"}},
        )

    patched_client(handler)
    result = CliRunner().invoke(cli_module.cli, ["subscribers", "list", "--limit", "3"])

    assert result.exit_code == 0, result.output
    assert "3 subscriber(s)." in result.output


def test_api_error_is_reported_cleanly(patched_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"errors": ["unauthorized"]})

    patched_client(handler)
    result = CliRunner().invoke(cli_module.cli, ["subscribers", "list"])

    assert result.exit_code != 0
    assert "Kit API error" in result.output


def test_empty_list(patched_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"subscribers": [], "pagination": {"has_next_page": False}})

    patched_client(handler)
    result = CliRunner().invoke(cli_module.cli, ["subscribers", "list"])

    assert result.exit_code == 0, result.output
    assert "No subscribers found." in result.output


# -- tags list / create ----------------------------------------------------


def test_tags_list_renders_catalog(patched_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "tags": [{"id": 1, "name": "VIP", "subscriber_count": 12}],
                "pagination": {"has_next_page": False},
            },
        )

    patched_client(handler)
    result = CliRunner().invoke(cli_module.cli, ["tags", "list"])

    assert result.exit_code == 0, result.output
    assert "VIP" in result.output
    assert "12" in result.output
    assert "1 tag(s)." in result.output


def test_tags_create(patched_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"tag": {"id": 9, "name": "Newsletter"}})

    patched_client(handler)
    result = CliRunner().invoke(cli_module.cli, ["tags", "create", "Newsletter"])

    assert result.exit_code == 0, result.output
    assert "Newsletter" in result.output
    assert "9" in result.output


# -- tags add / remove -----------------------------------------------------


def test_tags_add_dry_run_makes_no_mutations(patched_client):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v4/tags":
            return httpx.Response(
                200,
                json={"tags": [{"id": 5, "name": "VIP"}], "pagination": {"has_next_page": False}},
            )
        raise AssertionError(f"dry-run must not mutate; saw {request.method} {request.url.path}")

    patched_client(handler)
    result = CliRunner().invoke(cli_module.cli, ["tags", "add", "VIP", "1", "2", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "dry-run" in result.output
    assert "2 subscriber(s)" in result.output


def test_tags_add_requires_confirmation(patched_client):
    """Without --yes, answering 'n' aborts before any mutation."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v4/tags":
            return httpx.Response(
                200,
                json={"tags": [{"id": 5, "name": "VIP"}], "pagination": {"has_next_page": False}},
            )
        raise AssertionError("must not mutate when the user declines")

    patched_client(handler)
    result = CliRunner().invoke(cli_module.cli, ["tags", "add", "VIP", "1"], input="n\n")

    assert result.exit_code != 0  # click abort
    assert "automations" in result.output  # warning shown


def test_tags_add_yes_skips_confirm_and_reports_summary(patched_client):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v4/tags":
            return httpx.Response(
                200,
                json={"tags": [{"id": 5, "name": "VIP"}], "pagination": {"has_next_page": False}},
            )
        return httpx.Response(201, json={"subscriber": {"id": 1}})

    patched_client(handler)
    result = CliRunner().invoke(cli_module.cli, ["tags", "add", "VIP", "1", "--yes"])

    assert result.exit_code == 0, result.output
    assert "1 tagged, 0 failed." in result.output


def test_tags_add_by_id_uses_create_missing(patched_client):
    """--create-missing creates the tag when the name doesn't resolve."""
    posted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v4/tags" and request.method == "GET":
            return httpx.Response(200, json={"tags": [], "pagination": {"has_next_page": False}})
        if request.url.path == "/v4/tags" and request.method == "POST":
            posted.append("created")
            return httpx.Response(201, json={"tag": {"id": 77, "name": "Fresh"}})
        return httpx.Response(201, json={"subscriber": {"id": 1}})

    patched_client(handler)
    result = CliRunner().invoke(
        cli_module.cli, ["tags", "add", "Fresh", "1", "--create-missing", "--yes"]
    )

    assert result.exit_code == 0, result.output
    assert posted == ["created"]
    assert "1 tagged" in result.output


def test_tags_remove_reports_summary(patched_client):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v4/tags":
            return httpx.Response(
                200,
                json={"tags": [{"id": 5, "name": "VIP"}], "pagination": {"has_next_page": False}},
            )
        if request.url.path == "/v4/subscribers/1/tags":  # authoritative check: has the tag
            return httpx.Response(
                200, json={"tags": [{"id": 5}], "pagination": {"has_next_page": False}}
            )
        return httpx.Response(204)  # DELETE

    patched_client(handler)
    result = CliRunner().invoke(cli_module.cli, ["tags", "remove", "VIP", "1", "--yes"])

    assert result.exit_code == 0, result.output
    assert "1 removed, 0 weren't tagged, 0 failed." in result.output


def test_tags_remove_phantom_reports_not_tagged(patched_client):
    """A subscriber the tag index lists but who doesn't really have the tag is
    reported as 'weren't tagged', not a false 'removed' — and no DELETE fires."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v4/tags":
            return httpx.Response(
                200,
                json={"tags": [{"id": 5, "name": "VIP"}], "pagination": {"has_next_page": False}},
            )
        if request.url.path == "/v4/subscribers/1/tags":
            return httpx.Response(200, json={"tags": [], "pagination": {"has_next_page": False}})
        raise AssertionError("must not DELETE when the subscriber isn't really tagged")

    patched_client(handler)
    result = CliRunner().invoke(cli_module.cli, ["tags", "remove", "VIP", "1", "--yes"])

    assert result.exit_code == 0, result.output
    assert "0 removed, 1 weren't tagged, 0 failed." in result.output


def test_tags_remove_all_scopes_to_tag_holders(patched_client):
    """`remove --all` enumerates the tag's subscribers (never scanning the whole
    account), verifies each really has the tag, then deletes only those."""
    deletes: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        if path == "/v4/tags" and method == "GET":
            return httpx.Response(
                200,
                json={"tags": [{"id": 5, "name": "VIP"}], "pagination": {"has_next_page": False}},
            )
        if path == "/v4/tags/5/subscribers" and method == "GET":
            assert request.url.params["status"] == "all"
            return httpx.Response(
                200,
                json={
                    "subscribers": [{"id": 1}, {"id": 2}],
                    "pagination": {"has_next_page": False},
                },
            )
        if path in ("/v4/subscribers/1/tags", "/v4/subscribers/2/tags") and method == "GET":
            return httpx.Response(
                200, json={"tags": [{"id": 5}], "pagination": {"has_next_page": False}}
            )
        if method == "DELETE":
            deletes.append(path)
            return httpx.Response(204)
        raise AssertionError(f"unexpected call {method} {path} (did it scan all subscribers?)")

    patched_client(handler)
    result = CliRunner().invoke(cli_module.cli, ["tags", "remove", "VIP", "--all", "--yes"])

    assert result.exit_code == 0, result.output
    assert "2 removed, 0 weren't tagged, 0 failed." in result.output
    assert deletes == ["/v4/tags/5/subscribers/1", "/v4/tags/5/subscribers/2"]


def test_tags_add_from_stdin(patched_client):
    """--from-file - reads ids/emails from stdin."""
    tagged: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v4/tags":
            return httpx.Response(
                200,
                json={"tags": [{"id": 5, "name": "VIP"}], "pagination": {"has_next_page": False}},
            )
        tagged.append(request.url.path)
        return httpx.Response(201, json={"subscriber": {}})

    patched_client(handler)
    result = CliRunner().invoke(
        cli_module.cli,
        ["tags", "add", "VIP", "--from-file", "-", "--yes"],
        input="1\n2\n# comment\n\n3\n",
    )

    assert result.exit_code == 0, result.output
    assert "3 tagged" in result.output
    assert len(tagged) == 3


def test_tags_add_no_selection_errors(patched_client):
    patched_client(lambda r: httpx.Response(200))
    result = CliRunner().invoke(cli_module.cli, ["tags", "add", "VIP"])

    assert result.exit_code != 0
    assert "No subscribers selected" in result.output


def test_tags_add_failure_exits_nonzero(patched_client):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v4/tags":
            return httpx.Response(
                200,
                json={"tags": [{"id": 5, "name": "VIP"}], "pagination": {"has_next_page": False}},
            )
        return httpx.Response(404, json={"errors": ["not found"]})

    patched_client(handler)
    result = CliRunner().invoke(cli_module.cli, ["tags", "add", "VIP", "999", "--yes"])

    assert result.exit_code != 0
    assert "0 tagged, 1 failed." in result.output
    assert "Failures:" in result.output


def test_tags_remove_all_nonexistent_id_reported_cleanly(patched_client):
    """`remove <bad-id> --all` reports a clean 'no tag' message, not a raw 404."""

    def handler(request: httpx.Request) -> httpx.Response:
        # numeric tag id skips the /v4/tags lookup; the tag-subscribers list 404s
        return httpx.Response(404, json={"errors": ["Not Found"]})

    patched_client(handler)
    result = CliRunner().invoke(cli_module.cli, ["tags", "remove", "999999", "--all", "--yes"])

    assert result.exit_code != 0
    assert "No tag with id 999999" in result.output
    assert "Kit API error" not in result.output


def test_tags_unknown_name_reported_cleanly(patched_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"tags": [], "pagination": {"has_next_page": False}})

    patched_client(handler)
    result = CliRunner().invoke(cli_module.cli, ["tags", "add", "Ghost", "1", "--yes"])

    assert result.exit_code != 0
    assert "No tag named" in result.output
