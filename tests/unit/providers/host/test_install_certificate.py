"""``HostProvider.install_certificate``: the optional install hook (#1682)."""

from __future__ import annotations

import pytest

from infrafoundry.core.certs.install import resolve_target
from infrafoundry.core.certs.models import CertificateInstallError
from infrafoundry.core.certs.ssh_installer import SshCertificateInstaller
from infrafoundry.core.protocols import InstallsCertificate
from infrafoundry.providers.host import HostProvider
from tests.unit.core.certs.fakes import FakeRun, certificate_resource, host_resource

pytestmark = pytest.mark.unit

KEY = "-----BEGIN " + "PRIVATE KEY-----\nSENTINEL-NOT-A-REAL-KEY\n-----END " + "PRIVATE KEY-----\n"


def resolved() -> object:
    return resolve_target(
        certificate_resource().config["target"], ["example.com"], [host_resource()]
    )


def test_the_host_provider_implements_the_protocol(provider: HostProvider) -> None:
    assert isinstance(provider, InstallsCertificate)


def test_install_goes_through_the_ssh_installer(provider: HostProvider) -> None:
    run = FakeRun()
    provider._certificate_installer = SshCertificateInstaller(run)
    provider.install_certificate(resolved(), "CERT\n", "CHAIN\n", KEY)  # type: ignore[arg-type]
    assert run.calls[0][1]["input"] == "CERT\nCHAIN\n"
    assert run.calls[1][1]["input"] == KEY
    assert all("SENTINEL" not in " ".join(argv) for argv, _ in run.calls)


def test_a_failure_surfaces_as_a_certificate_install_error(provider: HostProvider) -> None:
    provider._certificate_installer = SshCertificateInstaller(FakeRun(returncode=255))
    with pytest.raises(CertificateInstallError, match="failed"):
        provider.install_certificate(resolved(), "C", "", KEY)  # type: ignore[arg-type]
