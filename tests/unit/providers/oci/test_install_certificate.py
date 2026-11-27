"""``OCIProvider.install_certificate``: the optional install hook (#1682)."""

from __future__ import annotations

from pathlib import Path

import pytest

from infrafoundry.core.certs.install import CertificateTarget, resolve_target
from infrafoundry.core.certs.models import CertificateInstallError
from infrafoundry.core.certs.ssh_installer import SshCertificateInstaller
from infrafoundry.core.protocols import InstallsCertificate
from infrafoundry.providers.oci import OCIProvider
from tests.unit.core.certs.fakes import FakeRun, vm_resource, vm_target

pytestmark = pytest.mark.unit

KEY = "-----BEGIN " + "PRIVATE KEY-----\nSENTINEL-NOT-A-REAL-KEY\n-----END " + "PRIVATE KEY-----\n"


@pytest.fixture
def provider(tmp_path: Path) -> OCIProvider:
    return OCIProvider(tmp_path / "envs", tmp_path / "out")


def resolved() -> CertificateTarget:
    resource = vm_resource(provider="oci", rtype="instance", jumphost=None)
    return resolve_target(vm_target(resource), ["example.com"], [resource])


def test_the_provider_implements_the_protocol(provider: OCIProvider) -> None:
    assert isinstance(provider, InstallsCertificate)


def test_install_goes_through_the_ssh_installer(provider: OCIProvider) -> None:
    run = FakeRun()
    provider._certificate_installer = SshCertificateInstaller(run)
    provider.install_certificate(resolved(), "CERT\n", "CHAIN\n", KEY)
    assert run.calls[0][1]["input"] == "CERT\nCHAIN\n"
    assert run.calls[1][1]["input"] == KEY
    assert all("SENTINEL" not in " ".join(argv) for argv, _ in run.calls)


def test_a_failure_surfaces_as_a_certificate_install_error(provider: OCIProvider) -> None:
    provider._certificate_installer = SshCertificateInstaller(FakeRun(returncode=255))
    with pytest.raises(CertificateInstallError, match="failed"):
        provider.install_certificate(resolved(), "C", "", KEY)
