"""``CertificateService.plan``/``renew`` and the ``CERTIFICATE_*`` events."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.certs.install import CertificateTarget
from infrafoundry.core.certs.models import CertificateError, CertificateInstallError
from infrafoundry.core.certs.service import CertificateService
from infrafoundry.core.events.types import EventType

from .fakes import KEY_ARMOUR, NOW, TOKEN, certificate_resource, host_resource
from .test_service import DIRECTORY, ENVS, Rig, resources, stored_entry

pytestmark = pytest.mark.unit


class Bus:
    def __init__(self) -> None:
        self.events: list[tuple[EventType, dict[str, Any]]] = []
        self.error: Exception | None = None

    def __call__(self, event: EventType, data: dict[str, Any]) -> None:
        if self.error:
            raise self.error
        self.events.append((event, data))


def service(rig: Rig, bus: Bus) -> CertificateService:
    def verify(target: CertificateTarget, sha: str) -> None:
        rig.host.events.append("verify")

    return CertificateService(
        env="prod",
        envs_dir=ENVS,
        writer=rig.writer,  # type: ignore[arg-type]
        providers={"host": rig.host},
        verify=verify,
        now=lambda: NOW,
        emit=bus,
    )


def renew(rig: Rig, bus: Bus, res: list[Any], **kwargs: Any) -> Any:
    return service(rig, bus).renew(
        res, rig.issuer, None, directory=DIRECTORY, directory_id="staging", **kwargs
    )


def plan(rig: Rig, res: list[Any], **kwargs: Any) -> Any:
    return service(rig, Bus()).plan(res, directory=DIRECTORY, **kwargs)


def test_plan_lists_missing_due_and_not_installed_only() -> None:
    rig = Rig()
    res = resources(
        certificate_resource("never"),
        certificate_resource("fresh", stored=stored_entry(rig)),
        certificate_resource("late", stored=stored_entry(rig, days=10)),
        certificate_resource("pending", stored=stored_entry(rig, installed=False)),
    )
    got = {p.name: (p.action, p.reason) for p in plan(rig, res)}
    assert set(got) == {"never", "late", "pending"}
    assert got["never"] == ("issue", "never issued")
    assert got["late"][0] == "issue" and got["late"][1].startswith("due")
    assert got["pending"] == ("install", "stored but not installed")


def test_plan_honours_the_per_certificate_window() -> None:
    rig = Rig()
    entry = stored_entry(rig, days=50)
    assert plan(rig, resources(certificate_resource(stored=entry))) == []
    wide = certificate_resource(stored=entry, renew_before_days=60)
    assert [p.action for p in plan(rig, resources(wide))] == ["issue"]


def test_plan_touches_no_network_writer_or_host() -> None:
    rig = Rig()
    plan(rig, resources(certificate_resource()))
    assert rig.acme.calls == []
    assert rig.dns.added == []
    assert rig.writer.history == []
    assert rig.host.events == []


def test_plan_reports_a_bad_declaration_and_rejects_unknown_names() -> None:
    rig = Rig()
    bad = certificate_resource(names=["192.0.2.1"])
    assert [p.action for p in plan(rig, resources(bad))] == ["error"]
    with pytest.raises(CertificateError, match="no certificate named: nope"):
        plan(rig, resources(certificate_resource()), only=["nope"])


def test_renew_issues_installs_and_publishes_events_in_order() -> None:
    rig, bus = Rig(), Bus()
    outcomes = renew(rig, bus, resources(certificate_resource()))
    assert [o.action for o in outcomes] == ["issued"]
    assert [e for e, _ in bus.events] == [
        EventType.CERTIFICATE_ISSUED,
        EventType.CERTIFICATE_INSTALLED,
    ]


def test_renew_skips_a_current_installed_certificate_without_events() -> None:
    rig, bus = Rig(), Bus()
    res = resources(certificate_resource(stored=stored_entry(rig)))
    assert [o.action for o in renew(rig, bus, res)] == ["skipped"]
    assert bus.events == [] and rig.acme.calls == []


def test_install_only_retry_publishes_only_installed() -> None:
    rig, bus = Rig(), Bus()
    res = resources(certificate_resource(stored=stored_entry(rig, installed=False)))
    assert [o.action for o in renew(rig, bus, res)] == ["installed"]
    assert [e for e, _ in bus.events] == [EventType.CERTIFICATE_INSTALLED]
    assert rig.acme.calls == []


def test_a_failure_publishes_certificate_failed_and_the_run_continues() -> None:
    rig, bus = Rig(), Bus()
    rig.host.error = CertificateInstallError("the reload failed")
    res = resources(certificate_resource("a"), certificate_resource("b"))
    outcomes = renew(rig, bus, res)
    assert [o.action for o in outcomes] == ["failed", "failed"]
    failed = [d for e, d in bus.events if e == EventType.CERTIFICATE_FAILED]
    assert [d["certificate"] for d in failed] == ["a", "b"]
    assert "the reload failed" in failed[0]["error"]


def test_payloads_carry_no_key_material_or_token() -> None:
    rig, bus = Rig(), Bus()
    rig.host.error = None
    renew(rig, bus, resources(certificate_resource()))
    text = repr(bus.events)
    for secret in (KEY_ARMOUR, "PRIVATE", "key_pem", TOKEN):
        assert secret not in text
    issued = bus.events[0][1]
    assert set(issued) == {"certificate", "names", "not_after", "sha256"}


def test_a_failing_subscriber_does_not_fail_the_run() -> None:
    rig, bus = Rig(), Bus()
    bus.error = RuntimeError("subscriber exploded")
    outcomes = renew(rig, bus, resources(certificate_resource()))
    assert [o.action for o in outcomes] == ["issued"]


def test_renew_only_processes_the_named_certificate() -> None:
    rig, bus = Rig(), Bus()
    res = [host_resource(), certificate_resource("a"), certificate_resource("b")]
    assert [o.name for o in renew(rig, bus, res, only=["b"])] == ["b"]
