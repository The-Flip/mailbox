"""Tests for the tag workflow layer (flipmail/tags.py).

Uses the ``make_client`` fixture (mock transport) from conftest — hermetic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import httpx
import pytest

from flipmail.tags import (
    TagResolutionError,
    Target,
    apply_tag,
    collect_targets,
    parse_target,
    resolve_tag,
)

if TYPE_CHECKING:
    from flipmail.tags import TagAction


def _tags_response(tags: list[dict]) -> httpx.Response:
    return httpx.Response(200, json={"tags": tags, "pagination": {"has_next_page": False}})


# -- resolve_tag -----------------------------------------------------------


def test_resolve_tag_by_name(make_client):
    with make_client(lambda r: _tags_response([{"id": 7, "name": "Volunteers"}])) as client:
        tag = resolve_tag(client, "volunteers")  # case-insensitive
    assert tag["id"] == 7


def test_resolve_tag_numeric_id_skips_lookup(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not call the API for a numeric tag id")

    with make_client(handler) as client:
        tag = resolve_tag(client, "42")
    assert tag["id"] == 42


def test_resolve_tag_not_found_raises(make_client):
    with make_client(lambda r: _tags_response([])) as client:
        with pytest.raises(TagResolutionError, match="No tag named"):
            resolve_tag(client, "Nope")


def test_resolve_tag_ambiguous_raises(make_client):
    tags = [{"id": 5, "name": "Dup"}, {"id": 9, "name": "Dup"}]
    with make_client(lambda r: _tags_response(tags)) as client:
        with pytest.raises(TagResolutionError, match="ambiguous"):
            resolve_tag(client, "Dup")


def test_resolve_tag_create_missing(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, json={"tag": {"id": 100, "name": "New"}})
        return _tags_response([])  # not found on lookup

    with make_client(handler) as client:
        tag = resolve_tag(client, "New", create_missing=True)
    assert tag == {"id": 100, "name": "New"}


# -- parse_target / collect_targets ---------------------------------------


def test_parse_target_email_vs_id():
    assert parse_target("a@b.co") == Target(email="a@b.co")
    assert parse_target("42") == Target(subscriber_id=42)
    with pytest.raises(ValueError):
        parse_target("not-an-id")


def test_collect_targets_parses_and_dedupes(make_client):
    with make_client(lambda r: httpx.Response(200)) as client:
        targets = collect_targets(client, tokens=["1", "a@b.co", "1", "a@b.co"])
    assert targets == [Target(subscriber_id=1), Target(email="a@b.co")]


def test_collect_targets_from_status_paginates(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["status"] == "active"
        return httpx.Response(
            200,
            json={
                "subscribers": [{"id": 1}, {"id": 2}],
                "pagination": {"has_next_page": False},
            },
        )

    with make_client(handler) as client:
        targets = collect_targets(client, from_status="active")
    assert [t.subscriber_id for t in targets] == [1, 2]


def test_collect_targets_within_tag_scopes_to_holders(make_client):
    """With within_tag_id, --all pulls from the tag's subscribers (status=all)."""
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        assert request.url.params["status"] == "all"
        return httpx.Response(
            200, json={"subscribers": [{"id": 7}], "pagination": {"has_next_page": False}}
        )

    with make_client(handler) as client:
        targets = collect_targets(client, all_subscribers=True, within_tag_id=5)

    assert [t.subscriber_id for t in targets] == [7]
    assert paths == ["/v4/tags/5/subscribers"]  # never scans GET /v4/subscribers


def test_collect_targets_within_tag_passes_from_status(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v4/tags/5/subscribers"
        assert request.url.params["status"] == "inactive"
        return httpx.Response(
            200, json={"subscribers": [{"id": 7}], "pagination": {"has_next_page": False}}
        )

    with make_client(handler) as client:
        targets = collect_targets(client, from_status="inactive", within_tag_id=5)
    assert [t.subscriber_id for t in targets] == [7]


def test_collect_targets_within_tag_404_raises_resolution_error(make_client):
    """A 404 listing a tag's subscribers means the tag id doesn't exist."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"errors": ["Not Found"]})

    with make_client(handler, max_retries=0) as client:
        with pytest.raises(TagResolutionError, match="No tag with id 5"):
            collect_targets(client, all_subscribers=True, within_tag_id=5)


# -- apply_tag -------------------------------------------------------------


def test_apply_tag_add_accumulates_successes(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"subscriber": {"id": 1}})

    with make_client(handler) as client:
        result = apply_tag(
            client, 5, [Target(subscriber_id=1), Target(subscriber_id=2)], action="add"
        )

    assert len(result.successes) == 2
    assert not result.failures


def test_apply_tag_records_failures_and_continues(make_client):
    """A 404 on one target is recorded; the batch keeps going."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/subscribers/2"):
            return httpx.Response(404, json={"errors": ["not found"]})
        return httpx.Response(201, json={"subscriber": {"id": 1}})

    targets = [Target(subscriber_id=1), Target(subscriber_id=2), Target(subscriber_id=3)]
    with make_client(handler, max_retries=0) as client:
        result = apply_tag(client, 5, targets, action="add")

    assert len(result.successes) == 2
    assert len(result.failures) == 1
    assert result.failures[0].target.subscriber_id == 2


def test_apply_tag_rejects_unknown_action(make_client):
    """An unexpected action raises instead of silently removing tags."""
    with make_client(lambda r: httpx.Response(200)) as client:
        with pytest.raises(ValueError, match="Unsupported tag action"):
            apply_tag(client, 5, [Target(subscriber_id=1)], action=cast("TagAction", "sync"))


def test_apply_tag_remove_deletes_when_tag_present(make_client):
    """Remove verifies the tag is really there, then DELETEs and counts it."""
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "GET":  # authoritative per-subscriber tag list
            return httpx.Response(
                200,
                json={"tags": [{"id": 5, "name": "VIP"}], "pagination": {"has_next_page": False}},
            )
        return httpx.Response(204)  # DELETE

    with make_client(handler) as client:
        result = apply_tag(client, 5, [Target(subscriber_id=1)], action="remove")

    assert calls == [("GET", "/v4/subscribers/1/tags"), ("DELETE", "/v4/tags/5/subscribers/1")]
    assert len(result.successes) == 1
    assert not result.skipped


def test_apply_tag_remove_skips_phantom_without_deleting(make_client):
    """If the subscriber doesn't really have the tag, skip — no DELETE, not a false success."""
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, json={"tags": [], "pagination": {"has_next_page": False}})
        raise AssertionError("must not DELETE a tag the subscriber doesn't have")

    with make_client(handler) as client:
        result = apply_tag(client, 5, [Target(subscriber_id=1)], action="remove")

    assert methods == ["GET"]  # checked, then skipped
    assert not result.successes
    assert len(result.skipped) == 1
    assert result.skipped[0].detail == "was not tagged"


def test_apply_tag_remove_by_email_resolves_id(make_client):
    """An email target is resolved to an id before verifying/removing."""
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/v4/subscribers" and request.url.params.get("email_address"):
            return httpx.Response(
                200, json={"subscribers": [{"id": 9}], "pagination": {"has_next_page": False}}
            )
        if request.url.path == "/v4/subscribers/9/tags":
            return httpx.Response(
                200, json={"tags": [{"id": 5}], "pagination": {"has_next_page": False}}
            )
        return httpx.Response(204)

    with make_client(handler) as client:
        result = apply_tag(client, 5, [Target(email="a@b.co")], action="remove")

    assert "/v4/tags/5/subscribers/9" in paths  # deleted by the resolved id
    assert len(result.successes) == 1


def test_apply_tag_remove_unknown_email_is_failure(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"subscribers": [], "pagination": {"has_next_page": False}})

    with make_client(handler) as client:
        result = apply_tag(client, 5, [Target(email="ghost@b.co")], action="remove")

    assert not result.successes
    assert len(result.failures) == 1
    assert "no such subscriber" in result.failures[0].detail
