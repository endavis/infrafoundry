"""The shared NetApp service layer, driven through real pynetappfoundry objects.

A tiny OpenAPI spec lives in ``tmp_path``, the HTTP session is a fake, and nothing touches a
cluster. A pynetappfoundry upgrade that breaks the in-memory adapter fails here.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

import pytest
import requests

pytest.importorskip("pynetappfoundry")

from infrafoundry.providers._netapp import (
    NetAppDependencyError,
    require_pynetappfoundry,
)
from infrafoundry.providers._netapp.ontap import (
    ConnectionParams,
    OntapAPIError,
    OntapConnectionError,
    OntapSpecMissingError,
    connect_ontap,
)

pytestmark = pytest.mark.unit

PIN = "ab" * 32
PASSWORD = "pw-example-not-secret"
JOB = "0b1c2d3e-0000-4000-8000-000000000001"
LIF_PATH = "/network/ip/interfaces"
SPEC: dict[str, Any] = {
    "paths": {
        LIF_PATH: {"get": {}, "post": {}},
        f"{LIF_PATH}/{{uuid}}": {"patch": {}, "delete": {}},
    }
}
ROW = {
    "uuid": "u1",
    "name": "lif1",
    "scope": "svm",
    "svm": {"name": "svm1"},
    "ip": {"address": "192.0.2.10", "netmask": "24"},
    "location": {
        "home_node": {"name": "cluster1-01"},
        "home_port": {"name": "e0d"},
        "auto_revert": False,
        "is_home": True,
    },
    "service_policy": {"name": "default-data-files"},
}


class FakeSession(requests.Session):
    """Records requests and answers from a queue of canned responses."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, str, Any]] = []
        self.responses: list[tuple[int, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:  # type: ignore[override]
        self.calls.append((method, url, kwargs.get("json")))
        status, body = self.responses.pop(0) if self.responses else (200, {"records": [ROW]})
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps(body).encode()
        response.headers["Content-Type"] = "application/json"
        response.url = url
        return response


@pytest.fixture
def spec_file(tmp_path: Path) -> Path:
    path = tmp_path / "apis" / "ontap" / "all.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(SPEC))
    return path


def _params(spec_file: Path, **changes: Any) -> ConnectionParams:
    values: dict[str, Any] = {
        "host": "192.0.2.1",
        "username": "admin-example",
        "password": PASSWORD,
        "fingerprint": PIN,
        "ca_bundle": None,
        "verify_ssl": None,
        "timeout": 5,
        "spec_file": spec_file,
    }
    values.update(changes)
    return ConnectionParams(**values)


@pytest.fixture
def session() -> FakeSession:
    return FakeSession()


def _tree(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*")}


def test_reads_and_writes_send_the_expected_requests(spec_file: Path, session: FakeSession) -> None:
    service = connect_ontap(_params(spec_file), session=session)
    rows = service.list_interfaces(["svm1"])
    assert [r["name"] for r in rows] == ["lif1"] and rows[0]["uuid"] == "u1"
    session.responses = [(201, {})]
    service.create_interface(
        **{
            "name": "lif2",
            "svm.name": "svm1",
            "ip.address": "192.0.2.11",
            "ip.netmask": "24",
            "location.home_node.name": "cluster1-01",
            "location.home_port.name": "e0d",
            "location.home_port.node.name": "cluster1-01",
            "service_policy.name": "default-data-files",
            "location.auto_revert": True,
        }
    )
    session.responses = [(200, {})]
    service.update_interface("u1", **{"location.auto_revert": True})
    session.responses = [(200, {})]
    service.delete_interface("u1")

    (m1, u1, b1), (m2, u2, b2), (m3, u3, b3), (m4, u4, b4) = session.calls
    assert (m1, b1) == ("GET", None)
    assert u1 == "https://192.0.2.1/api/network/ip/interfaces?fields=%2A&svm.name=svm1"
    assert (m2, u2) == ("POST", "https://192.0.2.1/api/network/ip/interfaces")
    assert b2 == {
        "name": "lif2",
        "svm": {"name": "svm1"},
        "ip": {"address": "192.0.2.11", "netmask": "24"},
        "location": {
            "home_node": {"name": "cluster1-01"},
            "home_port": {"name": "e0d", "node": {"name": "cluster1-01"}},
            "auto_revert": True,
        },
        "service_policy": {"name": "default-data-files"},
    }
    assert (m3, u3, b3) == (
        "PATCH",
        "https://192.0.2.1/api/network/ip/interfaces/u1",
        {"location": {"auto_revert": True}},
    )
    assert (m4, u4, b4) == ("DELETE", "https://192.0.2.1/api/network/ip/interfaces/u1", None)


def test_a_write_waits_for_its_job(spec_file: Path, session: FakeSession) -> None:
    service = connect_ontap(_params(spec_file), session=session)
    session.responses = [
        (202, {"job": {"uuid": JOB, "_links": {"self": {"href": f"/api/cluster/jobs/{JOB}"}}}}),
        (200, {"uuid": JOB, "state": "success", "message": "Complete: Success"}),
    ]
    service.update_interface("u1", **{"location.auto_revert": True})
    assert [c[0] for c in session.calls] == ["PATCH", "GET"]
    assert JOB in session.calls[1][1]


def test_a_failed_job_becomes_an_api_error(spec_file: Path, session: FakeSession) -> None:
    service = connect_ontap(_params(spec_file), session=session)
    session.responses = [
        (202, {"job": {"uuid": JOB, "_links": {"self": {"href": f"/api/cluster/jobs/{JOB}"}}}}),
        (
            200,
            {
                "uuid": JOB,
                "state": "failure",
                "message": "Failed",
                "error": {"message": "address is in use", "code": "1966"},
            },
        ),
    ]
    with pytest.raises(OntapAPIError, match="address is in use"):
        service.update_interface("u1", **{"location.auto_revert": True})


def test_an_http_error_carries_ontaps_message_and_no_credential(
    spec_file: Path, session: FakeSession
) -> None:
    service = connect_ontap(_params(spec_file), session=session)
    session.responses = [(400, {"error": {"message": "duplicate address", "code": "1376"}})]
    with pytest.raises(OntapAPIError) as caught:
        service.create_interface(name="lif2", **{"svm.name": "svm1"})
    assert "duplicate address" in str(caught.value) and "(code 1376)" in str(caught.value)
    assert PASSWORD not in str(caught.value)


def test_nothing_is_written_to_disk(
    spec_file: Path, session: FakeSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    before = _tree(tmp_path)
    service = connect_ontap(_params(spec_file, fingerprint=None, verify_ssl=False), session=session)
    service.list_interfaces(["svm1"])
    session.responses = [(200, {})]
    service.update_interface("u1", **{"location.auto_revert": True})
    assert _tree(tmp_path) == before
    assert os.listdir(work) == []


def test_credentials_stay_out_of_debug_logs(
    spec_file: Path, session: FakeSession, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    service = connect_ontap(_params(spec_file), session=session)
    service.list_interfaces(["svm1"])
    session.responses = [(200, {})]
    service.update_interface("u1", **{"location.auto_revert": True})
    token = base64.b64encode(f"admin-example:{PASSWORD}".encode()).decode()
    assert PASSWORD not in caplog.text and token not in caplog.text


def test_cluster_info_and_names(spec_file: Path, session: FakeSession) -> None:
    service = connect_ontap(_params(spec_file), session=session)
    session.responses = [(200, {"name": "cluster1", "version": {"full": "9.18.1"}})]
    assert service.cluster_info()["version"]["full"] == "9.18.1"
    session.responses = [(200, {"records": [{"name": "svm1"}, {"name": "svm2"}]})]
    assert service.list_names("svms") == {"svm1", "svm2"}
    session.responses = [(200, {"records": [{"name": "e0d", "node": {"name": "cluster1-01"}}]})]
    assert service.list_names("ports") == {"cluster1-01:e0d"}
    assert "fields=name%2Cnode.name" in session.calls[-1][1]


def test_trust_modes_reach_the_client(
    spec_file: Path, session: FakeSession, tmp_path: Path
) -> None:
    bundle = tmp_path / "ca.pem"
    bundle.write_text("-----BEGIN CERTIFICATE-----\n")
    pinned = connect_ontap(_params(spec_file), session=session)
    assert pinned._client.verify_ssl is False  # type: ignore[attr-defined]
    unverified = connect_ontap(_params(spec_file, fingerprint=None, verify_ssl=False))
    assert unverified._client.verify_ssl is False  # type: ignore[attr-defined]
    chain = connect_ontap(_params(spec_file, fingerprint=None, verify_ssl=True))
    assert chain._client.verify_ssl is True  # type: ignore[attr-defined]
    bundled = connect_ontap(_params(spec_file, fingerprint=None, ca_bundle=bundle))
    assert bundled._client.verify_ssl == str(bundle)  # type: ignore[attr-defined]


def test_pin_store_answers_the_pin_without_disk_io(tmp_path: Path) -> None:
    from infrafoundry.providers._netapp._adapter import PinnedFingerprintStore

    def never(_host: str, _port: int) -> bytes:
        raise AssertionError("a pinned store must not fetch the certificate")

    store = PinnedFingerprintStore(PIN, never)
    assert store.get_fingerprint("192.0.2.1", 443) == PIN
    assert not store.path.exists()


def test_unverified_store_remembers_the_first_certificate_in_memory_only() -> None:
    from infrafoundry.providers._netapp._adapter import PinnedFingerprintStore

    seen: list[str] = []

    def fetch(host: str, port: int) -> bytes:
        seen.append(f"{host}:{port}")
        return b"der-bytes-example"

    store = PinnedFingerprintStore(None, fetch)
    expected = hashlib.sha256(b"der-bytes-example").hexdigest()
    assert store.get_fingerprint("192.0.2.1") == expected
    assert store.get_fingerprint("192.0.2.1") == expected
    assert seen == ["192.0.2.1:443"] and not store.path.exists()


def test_a_pin_mismatch_says_to_re_pin(spec_file: Path, session: FakeSession) -> None:
    from pynetappfoundry.clients.trust import HostIdentityChangedError

    service = connect_ontap(_params(spec_file), session=session)

    def mismatch(*_a: Any, **_k: Any) -> Any:
        raise HostIdentityChangedError("192.0.2.1:443", Path("x"), "reset", detail="changed")

    session.request = mismatch  # type: ignore[method-assign]
    with pytest.raises(OntapConnectionError, match="re-pin tls_fingerprint"):
        service.list_interfaces(["svm1"])


def test_unreachable_cluster_is_a_connection_error(spec_file: Path, session: FakeSession) -> None:
    service = connect_ontap(_params(spec_file), session=session)

    def down(*_a: Any, **_k: Any) -> Any:
        raise requests.ConnectionError("password-looking-detail")

    session.request = down  # type: ignore[method-assign]
    with pytest.raises(OntapConnectionError) as caught:
        service.cluster_info()
    assert "password-looking-detail" not in str(caught.value)


def test_missing_spec_names_the_path_and_the_download_url(tmp_path: Path) -> None:
    missing = tmp_path / "apis" / "ontap" / "all.json"
    with pytest.raises(OntapSpecMissingError) as caught:
        connect_ontap(_params(missing))
    text = str(caught.value)
    assert str(missing) in text
    assert text.count("https://raw.githubusercontent.com/") == 1
    assert text.endswith("docs/example-config/apis/ontap/all.json to that path")


def test_the_install_hint_when_pynetappfoundry_is_absent(
    spec_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib

    real = importlib.import_module

    def blocked(name: str, package: str | None = None) -> Any:
        if name == "pynetappfoundry":
            raise ImportError("No module named 'pynetappfoundry'")
        return real(name, package)

    monkeypatch.setattr("infrafoundry.providers._netapp.importlib.import_module", blocked)
    with pytest.raises(NetAppDependencyError, match=r"infrafoundry\[netapp\]"):
        require_pynetappfoundry()
    with pytest.raises(NetAppDependencyError, match=r"infrafoundry\[netapp\]"):
        connect_ontap(_params(spec_file))
