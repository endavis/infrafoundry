"""``CloudflareDns`` with a fake HTTP session; the token must never leak."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.certs.dns_cloudflare import CloudflareDns
from infrafoundry.core.certs.models import DnsError

from .fakes import TOKEN, ZONE

pytestmark = pytest.mark.unit


class Response:
    def __init__(self, status: int = 200, body: dict[str, Any] | None = None) -> None:
        self.status_code = status
        self._body = body if body is not None else {"success": True, "result": {}}
        self.content = b"x"

    def json(self) -> dict[str, Any]:
        return self._body


class Session:
    def __init__(self, *responses: Response | BaseException) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        self.calls.append((method, url, kwargs))
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def dns(session: Session) -> CloudflareDns:
    return CloudflareDns(TOKEN, ZONE, session)


def test_add_txt_posts_the_record_with_the_comment_and_a_bearer_token() -> None:
    session = Session(Response(body={"success": True, "result": {"id": "rec-1"}}))
    record_id = dns(session).add_txt("_acme-challenge.example.com", "val", "infrafoundry-acme web")
    assert record_id == "rec-1"
    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url.endswith(f"/zones/{ZONE}/dns_records")
    assert kwargs["headers"] == {"Authorization": f"Bearer {TOKEN}"}
    assert kwargs["json"]["comment"] == "infrafoundry-acme web"
    assert kwargs["json"]["type"] == "TXT"


def test_errors_never_carry_the_token_or_zone() -> None:
    body = {"success": False, "errors": [{"message": f"bad {TOKEN} in {ZONE}"}]}
    with pytest.raises(DnsError) as caught:
        dns(Session(Response(403, body))).add_txt("n", "v", "c")
    assert TOKEN not in str(caught.value)
    assert ZONE not in str(caught.value)
    assert "HTTP 403" in str(caught.value)


def test_a_transport_error_is_scrubbed() -> None:
    with pytest.raises(DnsError) as caught:
        dns(Session(OSError(f"connect to {TOKEN} failed"))).add_txt("n", "v", "c")
    assert TOKEN not in str(caught.value)


def test_a_missing_record_id_is_an_error() -> None:
    with pytest.raises(DnsError, match="no record id"):
        dns(Session(Response(body={"success": True, "result": {}}))).add_txt("n", "v", "c")


def test_delete_treats_an_already_deleted_record_as_done() -> None:
    dns(Session(Response(404, {"success": False}))).delete("gone")


def test_delete_failure_raises() -> None:
    with pytest.raises(DnsError):
        dns(Session(Response(500, {"success": False}))).delete("rec-1")


def test_purge_stale_deletes_only_infrafoundry_records() -> None:
    listing = Response(
        body={
            "success": True,
            "result": [
                {"id": "a", "comment": "infrafoundry-acme web"},
                {"id": "b", "comment": "mine"},
                {"id": "c", "comment": None},
            ],
        }
    )
    session = Session(listing, Response())
    assert dns(session).purge_stale() == 1
    assert [c[0] for c in session.calls] == ["GET", "DELETE"]
    assert session.calls[0][2]["params"]["comment.startswith"] == "infrafoundry-acme"
    assert session.calls[1][1].endswith("/a")


def test_name_servers_reads_the_zone_with_a_bearer_token() -> None:
    body = {"success": True, "result": {"name_servers": ["a.ns.example.com", "b.ns.example.com"]}}
    session = Session(Response(body=body))
    assert dns(session).name_servers() == ["a.ns.example.com", "b.ns.example.com"]
    method, url, kwargs = session.calls[0]
    assert method == "GET"
    assert url.endswith(f"/zones/{ZONE}")
    assert kwargs["headers"] == {"Authorization": f"Bearer {TOKEN}"}


def test_a_refused_name_server_lookup_names_zone_read_and_leaks_nothing() -> None:
    body = {"success": False, "errors": [{"message": f"no {TOKEN} {ZONE}"}]}
    with pytest.raises(DnsError) as caught:
        dns(Session(Response(403, body))).name_servers()
    assert "Zone:Read" in str(caught.value)
    assert TOKEN not in str(caught.value)
    assert ZONE not in str(caught.value)


def test_an_empty_name_server_list_raises() -> None:
    body = {"success": True, "result": {"name_servers": []}}
    with pytest.raises(DnsError):
        dns(Session(Response(body=body))).name_servers()
