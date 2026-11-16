"""Unit tests for ``KeaHAValidator`` (#1392)."""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators import KeaHAValidator
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext


def _run(*resources: ResourceConfig) -> ValidationReport:
    report = ValidationReport()
    KeaHAValidator(report).validate(OPNsenseValidationContext(resources=list(resources)))
    return report


def _errors(*resources: ResourceConfig) -> list[str]:
    return [r.message for r in _run(*resources).results if r.level == ValidationLevel.ERROR]


def _ha(**config: Any) -> ResourceConfig:
    return ResourceConfig(
        name="kea.dhcp4.ha", type="kea.dhcp4.ha", provider="opnsense", config=config
    )


def _peer(name: str, role: str = "primary", url: str = "http://192.0.2.1:8001/", **kw: Any) -> Any:
    return ResourceConfig(
        name=name,
        type="kea.dhcp4.ha_peers",
        provider="opnsense",
        config={"name": name, "role": role, "url": url, **kw},
    )


A = _peer("fw-a")
B = _peer("fw-b", "standby", "http://192.0.2.2:8001/")


def test_enabled_with_primary_and_standby_passes() -> None:
    assert _errors(_ha(enabled=True, this_server_name="fw-a", max_unacked_clients=0), A, B) == []


def test_enabled_requires_one_primary_and_one_standby() -> None:
    assert len(_errors(_ha(enabled=True))) == 1
    assert len(_errors(_ha(enabled=True), A)) == 1
    assert len(_errors(_ha(enabled=True), A, _peer("fw-c"))) == 1
    assert len(_errors(_ha(enabled=True), A, B, _peer("fw-c", "standby"))) == 1


def test_this_server_name_must_match_a_peer() -> None:
    assert len(_errors(_ha(enabled=True, this_server_name="other"), A, B)) == 1
    assert _errors(_ha(enabled=True, this_server_name="fw-b"), A, B) == []


def test_empty_this_server_name_is_info() -> None:
    report = _run(_ha(enabled=True, this_server_name=""), A, B)
    assert [r for r in report.results if r.level == ValidationLevel.ERROR] == []
    infos = [r for r in report.results if r.level == ValidationLevel.INFO]
    assert len(infos) == 1
    assert infos[0].passed is True
    assert "hostname" in infos[0].message
    assert not [r for r in report.results if r.level == ValidationLevel.WARNING]


def test_disabled_does_not_enforce_peer_count() -> None:
    assert _errors(_ha(enabled=False), A) == []
    assert _errors(A) == []
    assert len(_errors(_ha(enabled=False), _peer("x", "master"))) == 1


def test_peer_row_errors() -> None:
    assert len(_errors(_peer("a", "master"))) == 1
    assert len(_errors(_peer("a", url="ftp://192.0.2.1"))) == 1
    assert len(_errors(_peer("a", url="http://"))) == 1
    assert len(_errors(_peer("a", lock="yes"))) == 1
    assert len(_errors(_peer("a", bogus=1))) == 1
    missing = ResourceConfig(name="a", type="kea.dhcp4.ha_peers", provider="opnsense", config={})
    assert len(_errors(missing)) == 2  # role and url


def test_peer_uuid_carries_a_hint() -> None:
    errors = _errors(_peer("a", uuid="u"))
    assert len(errors) == 1
    assert "box assigns" in errors[0]


def test_duplicate_peer_names() -> None:
    assert len(_errors(_peer("a"), _peer("a", "standby"))) == 1


def test_peer_messages_hide_urls() -> None:
    errors = _errors(_peer("a", url="ftp://192.0.2.77"))
    assert all("192.0.2.77" not in e for e in errors)


def test_settings_errors() -> None:
    assert len(_errors(_ha(bogus=1))) == 1
    assert len(_errors(_ha(enabled="yes"))) == 1
    assert len(_errors(_ha(this_server_name=3))) == 1
    assert len(_errors(_ha(max_unacked_clients=-1))) == 1
    assert len(_errors(_ha(max_unacked_clients="2"))) == 1
