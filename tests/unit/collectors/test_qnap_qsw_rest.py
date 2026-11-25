"""Tests for the QNAP QSW-M collector."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from infrafoundry.collectors.base import Artifact, CollectorConfigError, CollectorError
from infrafoundry.collectors.qnap_qsw_rest import (
    READ_SET,
    QnapQswRestCollector,
    artifact_name,
    normalize,
)
from infrafoundry.collectors.runner import collect_environment
from infrafoundry.providers.qnap.client import (
    QnapApiDriftError,
    QnapApiError,
    QnapAuthError,
    QnapError,
    QnapUnreachableError,
)
from infrafoundry.providers.qnap.settings import QnapSettings
from tests.unit.providers.qnap.qnap_fake import PASSWORD, USER, ServedQnap
from tests.unit.providers.qnap.qnap_fake import served_qnap as served_qnap  # fixture

from .conftest import FakeConfigManager, MakeDevice, ReversibleFakeEncryptor, make_env

pytestmark = pytest.mark.unit

SECRET_FILES = {
    "system-info.json",
    "users.json",
    "snmp-community.json",
    "snmp-security.json",
    "system-config.bin",
}
EXPORT_OPTS = {"tls_fingerprint": "ab" * 32, "native_export": True}
EXPORT = b"\x1f\x8b\x00binary-example"


class _FakeClient:
    def __init__(
        self,
        replies: dict[str, Any] | None = None,
        errors: dict[str, Exception] | None = None,
        raw: bytes | Exception = EXPORT,
    ) -> None:
        self.replies = replies or {}
        self.errors = errors or {}
        self.raw = raw
        self.events: list[tuple[str, str]] = []

    @contextmanager
    def session(self) -> Any:
        self.events.append(("session-enter", ""))
        try:
            yield
        finally:
            self.events.append(("session-exit", ""))

    def get(self, path: str, *, timeout: float | None = None) -> Any:
        self.events.append(("get", path))
        if path in self.errors:
            raise self.errors[path]
        return self.replies.get(path, [{"key": path, "val": 1}])

    def get_raw(self, path: str, *, timeout: float | None = None) -> bytes:
        self.events.append(("get_raw", path))
        if isinstance(self.raw, Exception):
            raise self.raw
        return self.raw


def _device(make_device: MakeDevice, **kw: Any) -> Any:
    values: dict[str, Any] = {
        "name": "switch-core",
        "type": "qnap-qsw-rest",
        "address": "https://192.0.2.3",
        "username": "admin-example",
        "options": {"tls_fingerprint": "ab" * 32},
    }
    values.update(kw)
    return make_device(**values)


def _collector(make_device: MakeDevice, client: _FakeClient, **kw: Any) -> QnapQswRestCollector:
    return QnapQswRestCollector(_device(make_device, **kw), lambda _s: client)


def _by_name(artifacts: list[Artifact]) -> dict[str, Artifact]:
    return {a.name: a for a in artifacts}


def test_artifact_name() -> None:
    assert artifact_name("ip/ipv4/route") == "ip-ipv4-route.json"
    assert artifact_name("vlan") == "vlan.json"


def test_normalize_is_key_order_independent() -> None:
    a = normalize({"b": 1, "a": [2, {"y": 1, "x": 2}]})
    b = normalize({"a": [2, {"x": 2, "y": 1}], "b": 1})
    assert a == b
    assert a.endswith(b"\n")


def test_read_set_in_one_session(make_device: MakeDevice) -> None:
    client = _FakeClient()
    artifacts = _collector(make_device, client, options=EXPORT_OPTS).collect()
    events = client.events
    assert events[0] == ("session-enter", "")
    assert events[-1] == ("session-exit", "")
    assert [p for k, p in events if k == "get"] == list(READ_SET)
    assert [p for k, p in events if k == "get_raw"] == ["system/config"]
    names = {a.name for a in artifacts}
    assert artifact_name("ip/ipv4/route") in names
    assert "ports-group.json" not in names
    assert "unavailable.json" in names


def test_secret_flags(make_device: MakeDevice) -> None:
    artifacts = _collector(make_device, _FakeClient(), options=EXPORT_OPTS).collect()
    assert {a.name for a in artifacts if a.secret_bearing} == SECRET_FILES
    assert not _by_name(artifacts)["unavailable.json"].secret_bearing
    assert _by_name(artifacts)["system-config.bin"].content == EXPORT


def test_unavailable_endpoints_are_recorded(make_device: MakeDevice) -> None:
    client = _FakeClient(
        errors={
            "ports/config": QnapApiDriftError("not json"),
            "system/syslog": QnapApiError("system/syslog", 500),
            "snmp/service": QnapApiError("snmp/service", 400),
        }
    )
    artifacts = _by_name(_collector(make_device, client).collect())
    assert json.loads(artifacts["unavailable.json"].content) == {
        "ports/config": "not-json",
        "snmp/service": "error 400",
        "system/syslog": "error 500",
    }
    for gone in ("ports-config.json", "system-syslog.json", "snmp-service.json"):
        assert gone not in artifacts


def test_unavailable_is_empty_object_when_all_served(make_device: MakeDevice) -> None:
    artifacts = _by_name(_collector(make_device, _FakeClient()).collect())
    assert json.loads(artifacts["unavailable.json"].content) == {}


def test_native_export_unavailable_is_recorded(make_device: MakeDevice) -> None:
    client = _FakeClient(raw=QnapApiDriftError("web page"))
    artifacts = _by_name(_collector(make_device, client, options=EXPORT_OPTS).collect())
    assert json.loads(artifacts["unavailable.json"].content) == {"system/config": "not-json"}
    assert "system-config.bin" not in artifacts


@pytest.mark.parametrize("options", [{}, {"native_export": False}])
def test_native_export_is_off_by_default(make_device: MakeDevice, options: dict[str, Any]) -> None:
    client = _FakeClient()
    device_options = {"tls_fingerprint": "ab" * 32, **options}
    artifacts = _collector(make_device, client, options=device_options).collect()
    assert not any(k == "get_raw" for k, _ in client.events)
    assert "system-config.bin" not in {a.name for a in artifacts}


def test_native_export_opt_in_is_stored_encrypted(make_device: MakeDevice) -> None:
    client = _FakeClient()
    artifacts = _by_name(_collector(make_device, client, options=EXPORT_OPTS).collect())
    assert ("get_raw", "system/config") in client.events
    assert artifacts["system-config.bin"].secret_bearing
    assert artifacts["system-config.bin"].content == EXPORT


@pytest.mark.parametrize("required", ["system/info", "firmware/info", "vlan"])
def test_required_endpoint_missing_fails_and_logs_out(
    make_device: MakeDevice, required: str
) -> None:
    client = _FakeClient(errors={required: QnapApiDriftError("not json")})
    with pytest.raises(CollectorError, match=required):
        _collector(make_device, client).collect()
    assert client.events[-1] == ("session-exit", "")


@pytest.mark.parametrize("error", [QnapAuthError("refused"), QnapUnreachableError("down")])
def test_fatal_errors_fail_the_device(make_device: MakeDevice, error: QnapError) -> None:
    client = _FakeClient(errors={"vlan/indexs": error})
    with pytest.raises(CollectorError, match="switch-core"):
        _collector(make_device, client).collect()
    assert client.events[-1] == ("session-exit", "")


def _capture(make_device: MakeDevice, **kw: Any) -> tuple[list[QnapSettings], QnapQswRestCollector]:
    seen: list[QnapSettings] = []

    def factory(settings: QnapSettings) -> _FakeClient:
        seen.append(settings)
        return _FakeClient()

    return seen, QnapQswRestCollector(_device(make_device, **kw), factory)


def test_settings_mapping(make_device: MakeDevice) -> None:
    seen, collector = _capture(
        make_device,
        options={"tls_fingerprint": "AB:" * 31 + "AB"},
        timeout=45,
    )
    collector.collect()
    assert seen[0].fingerprint == "ab" * 32
    assert seen[0].timeout == 45
    assert seen[0].api_url == "https://192.0.2.3"


def test_verify_ssl_false_without_pin_is_accepted(make_device: MakeDevice) -> None:
    seen, collector = _capture(make_device, options={}, verify_ssl=False)
    collector.collect()
    assert seen[0].fingerprint is None


def test_no_pin_is_a_config_error_naming_the_device(make_device: MakeDevice) -> None:
    _, collector = _capture(make_device, options={})
    with pytest.raises(CollectorConfigError, match="switch-core"):
        collector.collect()


def test_http_address_is_a_config_error(make_device: MakeDevice) -> None:
    _, collector = _capture(make_device, address="http://192.0.2.3")
    with pytest.raises(CollectorConfigError, match="https"):
        collector.collect()


def test_password_never_leaks(make_device: MakeDevice, caplog: pytest.LogCaptureFixture) -> None:
    client = _FakeClient(errors={"vlan": QnapAuthError("refused")})
    collector = _collector(make_device, client)
    with caplog.at_level(logging.DEBUG), pytest.raises(CollectorError) as caught:
        collector.collect()
    haystack = str(caught.value) + repr(caught.value) + caplog.text
    assert "CANARY-LOGIN-0001" not in haystack


def test_write_safety_against_fake_switch(make_device: MakeDevice, served_qnap: ServedQnap) -> None:
    state = served_qnap.state
    state.results["vlan"] = [{"key": "1", "val": []}]
    state.raw["system/config"] = EXPORT
    device = _device(
        make_device,
        address=served_qnap.api_url,
        username=USER,
        password=PASSWORD,
        options={"tls_fingerprint": served_qnap.fingerprint, "native_export": True},
    )
    artifacts = _by_name(QnapQswRestCollector(device).collect())
    assert artifacts["system-config.bin"].content == EXPORT
    assert "vlan.json" in artifacts
    unavailable = json.loads(artifacts["unavailable.json"].content)
    assert unavailable["ports/config"] == "error 404"
    posts = [(m, p) for m, p, _, _ in state.requests if m != "GET"]
    assert sorted(posts) == [("POST", "/api/v1/users/exit"), ("POST", "/api/v1/users/login")]
    assert state.logouts == 1
    assert state.logins == 1


def test_store_round_trip(tmp_path: Path) -> None:
    replies = {"vlan": [{"key": "1", "val": [1]}]}
    clients: list[_FakeClient] = []

    def build(replies: dict[str, Any]) -> Callable[[Any], QnapQswRestCollector]:
        def factory(device: Any) -> QnapQswRestCollector:
            client = _FakeClient(replies=replies)
            clients.append(client)
            return QnapQswRestCollector(device, lambda _s: client)

        return factory

    (tmp_path / "envs").mkdir()
    dev = {"name": "switch-core", "type": "qnap-qsw-rest", "address": "https://192.0.2.3",
           "username": "u", "password": "p", "options": EXPORT_OPTS}  # fmt: skip
    manager = FakeConfigManager(tmp_path / "envs", make_env([dev]))
    encryptor = ReversibleFakeEncryptor()

    def run(rep: dict[str, Any]) -> list[str]:
        report = collect_environment(
            manager, "test", registry={"qnap-qsw-rest": build(rep)}, encryptor=encryptor
        )
        assert not report.failed
        return sorted(c.path.name for c in report.changed)

    first = run(replies)
    assert "vlan.json" in first
    assert "users.json.sops.json" in first
    assert "system-config.bin.sops.json" in first
    out = tmp_path / "device-configs/test/switch-core"
    assert json.loads((out / "vlan.json").read_text())[0]["key"] == "1"
    assert run(replies) == []
    assert run({"vlan": [{"key": "2", "val": [1]}]}) == ["vlan.json"]
