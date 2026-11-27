"""``ProxmoxProvider.install_certificate``: the optional install hook (#1682)."""

from __future__ import annotations

from pathlib import Path

import pytest

from infrafoundry.core.certs.install import CertificateTarget, resolve_target
from infrafoundry.core.certs.models import CertificateInstallError
from infrafoundry.core.certs.ssh_installer import SshCertificateInstaller
from infrafoundry.core.protocols import InstallsCertificate
from infrafoundry.providers.proxmox import ProxmoxProvider
from tests.unit.core.certs.fakes import FakeRun, vm_resource, vm_target

pytestmark = pytest.mark.unit

KEY = "-----BEGIN " + "PRIVATE KEY-----\nSENTINEL-NOT-A-REAL-KEY\n-----END " + "PRIVATE KEY-----\n"


@pytest.fixture
def provider(tmp_path: Path) -> ProxmoxProvider:
    return ProxmoxProvider(tmp_path / "envs", tmp_path / "out")


def resolved() -> CertificateTarget:
    resource = vm_resource(provider="proxmox", rtype="vm")
    return resolve_target(vm_target(resource), ["example.com"], [resource])


def test_the_provider_implements_the_protocol(provider: ProxmoxProvider) -> None:
    assert isinstance(provider, InstallsCertificate)


def test_install_goes_through_the_ssh_installer(provider: ProxmoxProvider) -> None:
    run = FakeRun()
    provider._certificate_installer = SshCertificateInstaller(run)
    provider.install_certificate(resolved(), "CERT\n", "CHAIN\n", KEY)
    assert run.calls[0][1]["input"] == "CERT\nCHAIN\n"
    assert run.calls[1][1]["input"] == KEY
    assert all("SENTINEL" not in " ".join(argv) for argv, _ in run.calls)


def test_a_failure_surfaces_as_a_certificate_install_error(provider: ProxmoxProvider) -> None:
    provider._certificate_installer = SshCertificateInstaller(FakeRun(returncode=255))
    with pytest.raises(CertificateInstallError, match="failed"):
        provider.install_certificate(resolved(), "C", "", KEY)


def node_target() -> CertificateTarget:
    return resolve_target(
        {"provider": "proxmox", "kind": "node", "resource": "pve1"}, ["pve1.example.com"], []
    )


def test_a_node_target_uses_the_api_and_never_ssh(
    provider: ProxmoxProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import MagicMock

    run = FakeRun()
    provider._certificate_installer = SshCertificateInstaller(run)
    api = MagicMock()
    api.get_json.return_value = {"data": [{"node": "pve1"}]}
    monkeypatch.setattr(provider, "_api_client", lambda: api)
    provider.install_certificate(node_target(), "CERT\n", "CHAIN\n", KEY)
    assert run.calls == []
    endpoint, data = api.post_json.call_args.args
    assert endpoint == "nodes/pve1/certificates/custom"
    assert data["key"] == KEY


def test_a_node_target_without_credentials_fails(
    provider: ProxmoxProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(provider, "_api_client", lambda: None)
    with pytest.raises(CertificateInstallError, match="no Proxmox API credentials"):
        provider.install_certificate(node_target(), "C", "", KEY)


def test_a_vm_target_still_goes_over_ssh(provider: ProxmoxProvider) -> None:
    run = FakeRun()
    provider._certificate_installer = SshCertificateInstaller(run)
    provider.install_certificate(resolved(), "C\n", "", KEY)
    assert run.calls
