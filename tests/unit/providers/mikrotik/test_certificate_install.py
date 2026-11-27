"""Tests for the RouterOS certificate installer (a fake device; documentation values)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from infrafoundry.core.certs.install import CertificateTarget
from infrafoundry.core.certs.keys import describe
from infrafoundry.core.certs.models import CertificateInstallError
from infrafoundry.providers.mikrotik.client import RouterOSAPIError, RouterOSConnectionError
from infrafoundry.providers.mikrotik.components.certificate import (
    RouterOSCertificateInstaller,
    served_chain_validates,
)
from infrafoundry.providers.mikrotik.settings import MikroTikSettings

from .certificate_fake import FakeRouterOSCerts, make_cert

pytestmark = pytest.mark.unit

SETTINGS = MikroTikSettings("https://192.0.2.2", "admin", "pw-example", verify_ssl=False)
TARGET = CertificateTarget(
    provider="mikrotik",
    resource="edge-services",
    key_path="",
    verify_server_name="router.example.com",
    env="test",
)
LEAF, KEY = make_cert("router.example.com")
CHAIN, _ = make_cert("Example Intermediate")
SHA = describe(LEAF).sha256
BASE = f"infrafoundry-edge-services-{SHA[:12]}"
CHAIN_SHA = describe(CHAIN).sha256


class Rig:
    def __init__(self, device: FakeRouterOSCerts, *, validates: bool = False) -> None:
        self.device = device
        self.verified: list[tuple[CertificateTarget, str]] = []
        self.verify_error: CertificateInstallError | None = None
        self.factory_settings: list[MikroTikSettings] = []
        self.validating = FakeRouterOSCerts()
        self.validating_error: RouterOSConnectionError | None = None
        self.validates = validates

    def _verify(self, target: CertificateTarget, sha: str) -> None:
        self.verified.append((target, sha))
        if self.verify_error:
            raise self.verify_error

    def _factory(self, settings: MikroTikSettings) -> Any:
        self.factory_settings.append(settings)
        error = self.validating_error
        if error:
            self.validating.errors[("GET", "system/resource")] = error
        return self.validating

    def installer(self) -> RouterOSCertificateInstaller:
        return RouterOSCertificateInstaller(
            SETTINGS,
            self.device,
            client_factory=self._factory,
            verify=self._verify,
            validates=lambda address, port, name: self.validates,
        )

    def install(self, chain: str = CHAIN) -> None:
        self.installer().install(TARGET, LEAF, chain, KEY)


def rig(**kwargs: Any) -> Rig:
    return Rig(FakeRouterOSCerts(), **kwargs)


def test_install_runs_in_the_lock_out_safe_order() -> None:
    r = rig()
    r.device.add_row("certificate", name=f"infrafoundry-edge-services-{'a' * 12}", fingerprint="x")
    r.device.add_row("certificate", name="unrelated", fingerprint="y")

    r.install()

    d = r.device

    def first(verb: str, prefix: str) -> int:
        return next(i for i, c in enumerate(d.calls) if c[0] == verb and c[1].startswith(prefix))

    assert first("PUT", "file") < first("POST", "certificate/import")
    assert first("POST", "certificate/import") < first("PATCH", "ip/service")
    assert d.service_cert("api-ssl") == d.service_cert("www-ssl") == BASE
    assert d.service_cert("sstp") == ""
    assert d.tables["file"] == []
    assert BASE in d.cert_names()
    assert f"{BASE}-ca0" in d.cert_names()
    assert "unrelated" in d.cert_names()
    assert f"infrafoundry-edge-services-{'a' * 12}" not in d.cert_names()
    leaf = next(x for x in d.tables["certificate"] if x["name"] == BASE)
    assert leaf["private-key"] == "true"
    assert len(r.verified) == 1
    assert r.verified[0][1] == SHA
    patches = [c for c in d.calls if c[0] == "PATCH" and c[1].startswith("ip/service")]
    assert [c[1] for c in patches] == ["ip/service/*A", "ip/service/*B"]


def test_verification_targets_the_management_address_and_rest_port() -> None:
    r = rig()
    r.install()

    target, sha = r.verified[0]
    assert target.endpoint is not None
    assert target.endpoint.address == "192.0.2.2"
    assert (target.verify_port, target.verify_server_name) == (443, "router.example.com")
    assert sha == SHA


def test_an_explicit_verify_port_wins() -> None:
    r = rig()
    r.installer().install(replace(TARGET, verify_port=8443), LEAF, "", KEY)

    assert r.verified[0][0].verify_port == 8443


def test_without_a_chain_only_two_files_are_uploaded() -> None:
    r = rig()
    r.install(chain="")

    puts = [c for c in r.device.calls if c[0] == "PUT"]
    assert len(puts) == 2


def test_a_certificate_still_used_by_another_service_is_kept() -> None:
    r = rig()
    old = f"infrafoundry-edge-services-{'b' * 12}"
    r.device.add_row("certificate", name=old, fingerprint="x")
    for row in r.device.tables["ip/service"]:
        if row["name"] == "sstp":
            row["certificate"] = old

    r.install()

    assert old in r.device.cert_names()


def test_certificates_of_other_resources_are_never_deleted() -> None:
    r = rig()
    other = f"infrafoundry-other-{'c' * 12}"
    r.device.add_row("certificate", name=other, fingerprint="x")

    r.install()

    assert other in r.device.cert_names()


def test_an_import_without_the_private_key_fails_and_removes_what_it_imported() -> None:
    r = Rig(FakeRouterOSCerts(key_attaches=False))

    with pytest.raises(CertificateInstallError, match="without its private key"):
        r.install()

    d = r.device
    assert d.cert_names() == []
    assert d.tables["file"] == []
    assert not [c for c in d.calls if c[0] == "PATCH"]
    assert r.verified == []


def test_an_api_error_on_the_second_service_rolls_back() -> None:
    r = rig()
    r.device.errors[("PATCH", "ip/service/*B")] = RouterOSAPIError("boom", 400)

    with pytest.raises(CertificateInstallError, match="boom"):
        r.install()

    d = r.device
    assert d.service_cert("api-ssl") == d.service_cert("www-ssl") == "old-manual"
    assert d.cert_names() == []
    assert r.verified == []


def test_a_transport_error_on_the_last_patch_goes_on_to_verification() -> None:
    r = rig()
    r.device.errors[("PATCH", "ip/service/*B")] = RouterOSConnectionError("dropped")

    r.install()

    assert len(r.verified) == 1


def test_a_transport_error_on_the_first_patch_fails() -> None:
    r = rig()
    r.device.errors[("PATCH", "ip/service/*A")] = RouterOSConnectionError("dropped")

    with pytest.raises(CertificateInstallError, match="dropped"):
        r.install()

    assert r.verified == []
    assert r.device.cert_names() == []


def test_a_failed_verification_names_both_certificates_and_keeps_the_old_ones() -> None:
    r = rig()
    old = f"infrafoundry-edge-services-{'d' * 12}"
    r.device.add_row("certificate", name=old, fingerprint="x")
    r.verify_error = CertificateInstallError("it serves a different certificate")

    with pytest.raises(CertificateInstallError) as exc:
        r.install()

    message = str(exc.value)
    assert BASE in message
    assert "old-manual" in message
    assert "/ip service set api-ssl,www-ssl certificate=old-manual" in message
    assert old in r.device.cert_names()
    assert not [c for c in r.device.calls if c[0] == "DELETE" and "certificate" in c[1]]


def test_errors_carry_no_pem_text() -> None:
    r = rig()
    leaked = f"bad input:\n{KEY}\n{LEAF}"
    r.device.errors[("POST", "certificate/import")] = RouterOSAPIError(leaked, 400)

    with pytest.raises(CertificateInstallError) as exc:
        r.install()

    message = str(exc.value)
    assert "PRIVATE" not in message
    assert "BEGIN" not in message
    for line in KEY.splitlines()[1:-1]:
        assert line not in message
    assert r.device.tables["file"] == []


def test_a_lingering_file_is_reported() -> None:
    r = rig()
    r.device.errors[("DELETE", "file/*101")] = RouterOSAPIError("busy", 500)

    with pytest.raises(CertificateInstallError, match="could not be removed"):
        r.install()


def test_http_is_refused_before_any_call() -> None:
    device = FakeRouterOSCerts()
    installer = RouterOSCertificateInstaller(
        MikroTikSettings("http://192.0.2.2", "admin", "pw-example"), device
    )

    with pytest.raises(CertificateInstallError, match="plaintext"):
        installer.install(TARGET, LEAF, "", KEY)

    assert device.calls == []


def test_a_missing_service_is_reported() -> None:
    r = rig()
    r.device.tables["ip/service"] = [{".id": "*A", "name": "api-ssl", "certificate": ""}]

    with pytest.raises(CertificateInstallError, match="www-ssl"):
        r.install()

    assert not [c for c in r.device.calls if c[0] == "PUT"]


def test_a_certificate_that_does_not_validate_skips_the_client_check() -> None:
    r = rig(validates=False)
    r.install()

    assert r.factory_settings == []


def test_a_validating_certificate_is_checked_with_the_validating_client() -> None:
    r = rig(validates=True)
    r.install()

    assert [s.tls_server_name for s in r.factory_settings] == ["router.example.com"]
    assert ("GET", "system/resource") in r.validating.calls


def test_a_failing_validating_client_fails_the_install() -> None:
    r = rig(validates=True)
    r.validating_error = RouterOSConnectionError("validation failed")

    with pytest.raises(CertificateInstallError, match="validating client failed"):
        r.install()


def test_served_chain_validates_is_false_for_an_untrusted_certificate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ssl

    class _Sock:
        def __enter__(self) -> _Sock:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    class _Context:
        def wrap_socket(self, sock: object, server_hostname: str) -> object:
            raise ssl.SSLCertVerificationError("untrusted")

    monkeypatch.setattr("socket.create_connection", lambda *a, **k: _Sock())
    monkeypatch.setattr("ssl.create_default_context", lambda: _Context())

    assert served_chain_validates("192.0.2.2", 443, "router.example.com") is False


def test_served_chain_validation_requires_tls_1_2(monkeypatch: pytest.MonkeyPatch) -> None:
    import ssl

    contexts: list[ssl.SSLContext] = []
    real = ssl.create_default_context

    def _record() -> ssl.SSLContext:
        ctx = real()
        contexts.append(ctx)
        return ctx

    def _refuse(*args: object, **kwargs: object) -> object:
        raise OSError("no network in unit tests")

    monkeypatch.setattr("ssl.create_default_context", _record)
    monkeypatch.setattr("socket.create_connection", _refuse)

    with pytest.raises(OSError, match="no network"):
        served_chain_validates("192.0.2.2", 443, "router.example.com")

    assert contexts[0].minimum_version == ssl.TLSVersion.TLSv1_2
