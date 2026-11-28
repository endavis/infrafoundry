"""Tests for the ONTAP certificate installer (a fake cluster; documentation values)."""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.certs.install import CertificateTarget
from infrafoundry.core.certs.keys import describe
from infrafoundry.core.certs.models import CertificateInstallError
from infrafoundry.providers._netapp.ontap import OntapAPIError
from infrafoundry.providers.ontap.components.certificate import OntapCertificateInstaller
from infrafoundry.providers.ontap.settings import OntapSettings

from .certificate_fake import FakeCluster, make_cert

pytestmark = pytest.mark.unit

OLD, _ = make_cert("old.example.com")
LEAF, KEY = make_cert("cluster1.example.com")
CHAIN, _ = make_cert("Example Intermediate")
SHA = describe(LEAF).sha256
OLD_SHA = describe(OLD).sha256
NAME = f"infrafoundry-cluster-{SHA[:12]}"
SVM_NAME = f"infrafoundry-svm-svm1-{SHA[:12]}"
SETTINGS = OntapSettings(
    host="192.0.2.1",
    username="admin-example",
    password="pw-example",
    fingerprint=OLD_SHA,
    api_spec_dir=Path("/spec-example"),
)
TARGET = CertificateTarget(
    provider="ontap",
    resource="cluster",
    key_path="",
    verify_port=443,
    verify_server_name="cluster1.example.com",
    kind="cluster",
    env="test",
)
SVM_TARGET = replace(TARGET, resource="svm1", kind="svm", svm="svm1")


class Rig:
    def __init__(self, *, production: bool = False, settings: OntapSettings = SETTINGS) -> None:
        self.cluster = FakeCluster(OLD)
        self.cluster.production = production
        self.settings = settings
        self.verified: list[tuple[CertificateTarget, str]] = []
        self.verify_error: CertificateInstallError | None = None
        self.production = production
        self.sleeps = 0
        self.pin: str | None = OLD_SHA
        self.clock = 0.0

    def _verify(self, target: CertificateTarget, sha: str) -> None:
        self.verified.append((target, sha))
        if self.verify_error:
            raise self.verify_error

    def _sleep(self, seconds: float) -> None:
        self.sleeps += 1
        self.clock += seconds

    def installer(self) -> OntapCertificateInstaller:
        return OntapCertificateInstaller(
            self.settings,
            self.cluster.client("original", pin=self.pin),
            service_factory=self.cluster.factory,
            verify=self._verify,
            validates=lambda address, port, name: self.production,
            sleep=self._sleep,
            monotonic=lambda: self.clock,
            bind_window=30.0,
            interval=3.0,
        )

    def install(self, target: CertificateTarget = TARGET, chain: str = CHAIN) -> None:
        self.installer().install(target, LEAF, chain, KEY)

    def verbs(self, *verbs: str) -> list[tuple[str, str, Any]]:
        return [c for c in self.cluster.calls if c[1] in verbs]


def test_install_runs_in_the_lock_out_safe_order() -> None:
    r = Rig()
    r.cluster.add(f"infrafoundry-cluster-{'a' * 12}", OLD, svm=None)
    r.cluster.add("unrelated", OLD, svm=None)
    r.cluster.add("some-ca", OLD, svm=None, type="server_ca")
    r.cluster.add(f"infrafoundry-svm-svm1-{'b' * 12}", OLD, svm="svm1")

    r.install()

    c = r.cluster
    install = next(call for call in c.calls if call[1] == "install")
    bind = next(call for call in c.calls if call[1] == "bind")
    assert c.calls.index(install) < c.calls.index(bind)
    assert install[2]["name"] == NAME
    assert install[2]["common_name"] == "cluster1.example.com"
    assert install[2]["intermediates"] == [CHAIN.strip()]
    assert bind[0] == "original"
    assert c.certs[c.bindings[None]]["name"] == NAME
    # everything after the bind goes through a client pinned to the new leaf
    after = c.calls[c.calls.index(bind) + 1 :]
    assert after and all(call[0] == f"pinned:{SHA[:8]}" for call in after)
    assert c.names() == {NAME, "manual-old", "unrelated", "some-ca"}
    assert f"infrafoundry-svm-svm1-{'b' * 12}" in c.names("svm1")
    assert r.verified[0][1] == SHA


def test_verification_targets_the_management_address() -> None:
    r = Rig()
    r.install()
    target, sha = r.verified[0]
    assert target.endpoint is not None and target.endpoint.address == "192.0.2.1"
    assert (target.verify_port, target.verify_server_name) == (443, "cluster1.example.com")
    assert sha == SHA


def test_a_dropped_connection_during_the_cluster_bind_carries_on_to_polling() -> None:
    r = Rig()
    r.cluster.bind_drops = True

    r.install()

    assert r.cluster.certs[r.cluster.bindings[None]]["name"] == NAME


def test_a_bind_api_error_deletes_the_new_certificate() -> None:
    r = Rig()
    r.cluster.bind_error = OntapAPIError("web service rejected it")

    with pytest.raises(CertificateInstallError, match="web service rejected it"):
        r.install()

    assert r.cluster.names() == {"manual-old"}
    assert r.cluster.bindings[None] == r.cluster.old_uuid


def test_a_stuck_bind_deletes_the_new_certificate_when_the_old_one_is_still_bound() -> None:
    r = Rig()
    r.cluster.bind_ignored = True

    with pytest.raises(CertificateInstallError, match="previous certificate is still in use"):
        r.install()

    assert r.cluster.names() == {"manual-old"}
    assert r.sleeps > 0


def test_a_same_name_certificate_with_the_same_leaf_is_reused() -> None:
    r = Rig()
    uuid = r.cluster.add(NAME, LEAF, svm=None)

    r.install()

    assert not r.verbs("install")
    assert r.cluster.bindings[None] == uuid


def test_a_same_name_certificate_with_another_leaf_fails() -> None:
    r = Rig()
    r.cluster.add(NAME, OLD, svm=None)

    with pytest.raises(CertificateInstallError, match="different content"):
        r.install()

    assert not r.verbs("install", "bind")


def test_an_already_bound_certificate_is_only_verified() -> None:
    r = Rig()
    uuid = r.cluster.add(NAME, LEAF, svm=None)
    r.cluster.bindings[None] = uuid
    r.pin = SHA

    r.install()

    assert not r.verbs("install", "bind", "delete")
    assert r.verified


def test_an_install_api_error_stops_before_binding() -> None:
    r = Rig()
    r.cluster.install_error = OntapAPIError("Unsupported key type")

    with pytest.raises(CertificateInstallError, match="Unsupported key type"):
        r.install()

    assert not r.verbs("bind")


def test_a_served_mismatch_rolls_back() -> None:
    r = Rig()
    r.verify_error = CertificateInstallError("it serves a different certificate")

    with pytest.raises(CertificateInstallError, match="previous certificate is bound again"):
        r.install()

    c = r.cluster
    assert c.bindings[None] == c.old_uuid
    assert c.names() == {"manual-old"}
    rebind = [call for call in c.calls if call[1] == "bind"][1]
    assert rebind[0] == f"pinned:{SHA[:8]}"
    assert [call for call in c.calls if call[1] == "delete"][-1][0] == "original"


def test_a_failing_validating_client_rolls_back() -> None:
    r = Rig(production=True)
    r.cluster.production = False  # the cluster does not actually pass validation

    with pytest.raises(CertificateInstallError, match="validating client failed"):
        r.install()

    assert r.cluster.bindings[None] == r.cluster.old_uuid
    assert r.cluster.names() == {"manual-old"}


def test_a_failed_rollback_names_both_certificates_and_the_console_fix() -> None:
    r = Rig()
    r.verify_error = CertificateInstallError("it serves a different certificate")
    r.cluster.delete_errors.add(NAME)

    with pytest.raises(CertificateInstallError) as caught:
        r.install()

    message = str(caught.value)
    assert NAME in message
    assert r.cluster.old_uuid in message
    assert "cluster console" in message


def test_production_uses_the_validating_client_and_deletes_superseded() -> None:
    r = Rig(production=True)
    superseded = r.cluster.add(f"infrafoundry-cluster-{'a' * 12}", OLD, svm=None)

    r.install()

    assert any(call[0] == "validating" and call[1] == "cluster_info" for call in r.cluster.calls)
    assert superseded not in r.cluster.certs


def test_staging_builds_no_validating_client_and_warns_to_repin(
    caplog: pytest.LogCaptureFixture,
) -> None:
    r = Rig(production=False)

    with caplog.at_level(logging.WARNING):
        r.install()

    assert not any(call[0] == "validating" for call in r.cluster.calls)
    assert any("re-pin" in rec.message.lower() for rec in caplog.records)
    assert SHA not in caplog.text


def test_staging_without_a_pin_does_not_warn(caplog: pytest.LogCaptureFixture) -> None:
    r = Rig(production=False, settings=replace(SETTINGS, fingerprint=None, verify_ssl=False))
    r.cluster.certs[r.cluster.old_uuid]["name"] = "manual-old"

    with caplog.at_level(logging.WARNING):
        r.installer().install(TARGET, LEAF, CHAIN, KEY)

    assert not any("re-pin" in rec.message.lower() for rec in caplog.records)


def test_a_failing_superseded_delete_only_warns(caplog: pytest.LogCaptureFixture) -> None:
    r = Rig(production=True)
    stale = f"infrafoundry-cluster-{'a' * 12}"
    r.cluster.add(stale, OLD, svm=None)
    r.cluster.delete_errors.add(stale)

    with caplog.at_level(logging.WARNING):
        r.install()

    assert stale in r.cluster.names()
    assert "could not delete superseded" in caplog.text


def test_the_svm_path_binds_the_svm_and_skips_the_cluster_client() -> None:
    r = Rig(production=True)
    stale = r.cluster.add(f"infrafoundry-svm-svm1-{'a' * 12}", OLD, svm="svm1")
    foreign = r.cluster.add(f"infrafoundry-cluster-{'a' * 12}", OLD, svm=None)
    svm_target = replace(
        SVM_TARGET,
        endpoint=None,
        verify_server_name="svm1.example.com",
    )

    r.install(svm_target)

    c = r.cluster
    assert SVM_NAME in c.names("svm1")
    assert c.certs[c.bindings["svm-uuid-1"]]["name"] == SVM_NAME
    assert c.bindings[None] == c.old_uuid
    assert stale not in c.certs
    assert foreign in c.certs
    assert all(call[0] == "original" for call in c.calls)
    assert not any(call[1] == "cluster_info" for call in c.calls)


def test_an_svm_bind_connection_error_deletes_the_new_certificate() -> None:
    r = Rig()
    r.cluster.bind_error = OntapAPIError("svm web rejected")

    with pytest.raises(CertificateInstallError, match="svm web rejected"):
        r.install(SVM_TARGET)

    assert SVM_NAME not in r.cluster.names("svm1")


def test_the_common_name_falls_back_to_the_first_dns_name() -> None:
    leaf, key = make_cert(None, san="only-san.example.com")
    r = Rig()

    r.installer().install(TARGET, leaf, "", key)

    install = next(call for call in r.cluster.calls if call[1] == "install")
    assert install[2]["common_name"] == "only-san.example.com"
    assert install[2]["intermediates"] == []


def test_no_error_carries_pem_text() -> None:
    r = Rig()
    r.cluster.install_error = OntapAPIError(f"bad body {KEY.splitlines()[1]} {LEAF}")

    with pytest.raises(CertificateInstallError) as caught:
        r.install()

    text = str(caught.value)
    assert "BEGIN" not in text
    assert KEY.splitlines()[1] not in text
