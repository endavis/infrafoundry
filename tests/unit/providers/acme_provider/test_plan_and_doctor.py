"""``get_plan_notes`` (offline, never raises) and the Cloudflare connectivity check."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.provider import provider_plan_notes
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.acme import AcmeProvider
from tests.unit.core.certs.fakes import NOW, TOKEN, ZONE, certificate_resource
from tests.unit.core.certs.test_service import Rig, stored_entry

from .test_provider import GOOD, make_env

pytestmark = pytest.mark.unit


class Reply:
    def __init__(self, status: int, body: dict[str, Any]) -> None:
        self.status_code = status
        self._body = body
        self.content = b"x"

    def json(self) -> dict[str, Any]:
        return self._body


class Session:
    def __init__(self, reply: Reply | Exception) -> None:
        self.reply = reply
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> Reply:
        self.calls.append((method, url, kwargs))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.fixture
def provider(tmp_path: Path) -> AcmeProvider:
    p = AcmeProvider(tmp_path / "envs", tmp_path / "output")
    p.set_environment("test")
    p.clock = lambda: NOW
    return p


def test_notes_warn_about_never_issued_due_and_not_installed(provider: AcmeProvider) -> None:
    rig = Rig()
    res = [
        certificate_resource("never"),
        certificate_resource("fresh", stored=stored_entry(rig)),
        certificate_resource("late", stored=stored_entry(rig, days=10)),
        certificate_resource("pending", stored=stored_entry(rig, installed=False)),
    ]
    notes = provider.get_plan_notes(res)
    text = "\n".join(notes)
    assert "'never' has never been issued" in text
    assert "'late' is due for renewal (9 days left)" in text or "'late' is due" in text
    assert "'pending' is stored but not installed" in text
    assert "'fresh'" not in text
    assert "foundry certs renew" in notes[-1]


def test_no_notes_when_everything_is_current_or_nothing_declared(provider: AcmeProvider) -> None:
    assert provider.get_plan_notes([]) == []
    current = certificate_resource(stored=stored_entry(Rig()))
    assert provider.get_plan_notes([current]) == []


def test_notes_never_raise(provider: AcmeProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("store exploded")

    monkeypatch.setattr("infrafoundry.providers.acme.certificate_statuses", boom)
    assert provider.get_plan_notes([certificate_resource()]) == []
    monkeypatch.undo()
    garbage = certificate_resource(stored={"cert_pem": "not a pem"})
    assert any("unreadable" in n for n in provider.get_plan_notes([garbage]))
    assert provider_plan_notes(provider, [garbage])


def connectivity(provider: AcmeProvider, session: Session, env: Any = None) -> ValidationReport:
    provider.http_session = lambda: session
    report = ValidationReport()
    provider.validate_connectivity(env or make_env(GOOD), report)
    return report


def test_connectivity_succeeds_with_a_read_only_call(provider: AcmeProvider) -> None:
    session = Session(Reply(200, {"success": True, "result": []}))
    report = connectivity(provider, session)
    assert not report.has_errors()
    assert any(r.passed and r.check_name == "acme_cloudflare_token" for r in report.results)
    method, url, kwargs = session.calls[0]
    assert method == "GET" and "/dns_records" in url
    assert kwargs["headers"] == {"Authorization": "Bearer " + TOKEN}


def test_connectivity_failure_is_reported_without_the_token(provider: AcmeProvider) -> None:
    body = {"success": False, "errors": [{"message": f"bad token {TOKEN} for {ZONE}"}]}
    report = connectivity(provider, Session(Reply(403, body)), make_env(GOOD))
    assert report.has_errors()
    messages = " ".join(r.message for r in report.results)
    assert "HTTP 403" in messages
    assert TOKEN not in messages and ZONE not in messages


def test_a_transport_error_is_reported_by_class_only(provider: AcmeProvider) -> None:
    session = Session(OSError(f"connect failed for {TOKEN}"))
    report = connectivity(provider, session)
    assert report.has_errors()
    assert TOKEN not in " ".join(r.message for r in report.results)


def test_no_probe_when_the_settings_are_invalid(provider: AcmeProvider) -> None:
    session = Session(Reply(200, {"success": True}))
    report = connectivity(provider, session, make_env())
    assert report.has_errors()
    assert session.calls == []


def test_an_unexpected_exception_does_not_leak_its_message(provider: AcmeProvider) -> None:
    report = connectivity(provider, Session(ValueError(f"oops {TOKEN}")))
    assert TOKEN not in " ".join(r.message for r in report.results)


def test_unresolvable_secrets_fail_the_check_without_a_probe(
    provider: AcmeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError(f"sops failed near {TOKEN}")

    monkeypatch.setattr("infrafoundry.secrets.environment.resolved_provider_settings", broken)
    session = Session(Reply(200, {"success": True}))
    report = connectivity(provider, session)
    assert report.has_errors()
    assert session.calls == []
    messages = " ".join(r.message for r in report.results)
    assert "RuntimeError" in messages and TOKEN not in messages
