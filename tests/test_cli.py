"""Tests for the Click CLI.

The CLI builds a ``KitClient()`` with no args, so we patch that constructor to
return one wired to a mock transport — no network, no real key.
"""

from __future__ import annotations

import secrets

import httpx
import pytest
from click.testing import CliRunner

from mailbox import cli as cli_module
from mailbox.kit import KitClient

TEST_KEY = secrets.token_hex(16)


@pytest.fixture
def patched_client(monkeypatch):
    """Patch cli.KitClient so it uses a mock transport with the given handler."""

    def install(handler):
        def factory(*_args, **_kwargs):
            return KitClient(
                TEST_KEY,
                base_url="https://api.kit.com/v4",
                transport=httpx.MockTransport(handler),
            )

        monkeypatch.setattr(cli_module, "KitClient", factory)

    return install


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
