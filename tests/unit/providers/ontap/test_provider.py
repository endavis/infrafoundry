"""OntapProvider: registration, Terraform stub, rest_* delegation, lazy import."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from infrafoundry.core.certs.install import CertificateTarget
from infrafoundry.core.certs.models import CertificateInstallError
from infrafoundry.providers.ontap import OntapProvider, register
from infrafoundry.providers.ontap.settings import OntapSettingsError

from .conftest import FakeOntapService, lif, record

pytestmark = pytest.mark.unit


def _provider(tmp_path: Path) -> OntapProvider:
    provider = OntapProvider(tmp_path, tmp_path / "generated")
    provider.set_environment("test")
    return provider


def test_register_metadata() -> None:
    meta = register()
    assert meta.name == "ontap"
    assert meta.resource_types == ["network.ip.interface"]
    assert meta.provider_class is OntapProvider
    assert meta.cli_registration is None


def test_resource_types_dependencies_and_terraform_types(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    assert provider.get_resource_types() == ["network.ip.interface"]
    assert provider.get_dependencies() == {"network.ip.interface": []}
    assert provider.get_terraform_resource_types() == {
        "network.ip.interface": ["ontap_network_ip_interface"]
    }
    assert provider.deletable_types() == {"network.ip.interface"}
    assert provider.validate_config({}) and not provider.validate_config([])  # type: ignore[arg-type]


def test_generate_terraform_writes_an_empty_block(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    provider.generate_terraform([lif()])
    written = list((tmp_path / "generated").rglob("main.tf"))
    assert written and "terraform {}" in written[0].read_text()


def test_generate_ansible_creates_directories_and_the_hook_is_a_no_op(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    provider.generate_ansible([lif()])
    provider.generate_ontap_rest([lif()])


def test_rest_methods_delegate_to_the_manager(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    fake = FakeOntapService([record()])
    manager_module = "infrafoundry.providers.ontap.components.manager"
    with (
        patch(f"{manager_module}.default_service_factory", return_value=fake),
        patch(f"{manager_module}.resolve_host", return_value="192.0.2.250"),
    ):
        plan = provider.rest_plan("test", [lif(auto_revert=True)])
        assert plan.counts["update"] == 1 and fake.calls == []
        applied = provider.rest_apply("test", [lif(auto_revert=True)])
        assert applied.success and fake.writes == ["update"]
        assert provider.rest_resource_ids("test", [lif()]) == {"lif1": "uuid-svm1-lif1"}
        destroyed = provider.rest_destroy("test", [lif()])
        assert destroyed.success and fake.rows == []


def test_importing_the_provider_does_not_load_pynetappfoundry() -> None:
    code = (
        "import sys\n"
        "import infrafoundry.providers.ontap\n"
        "import infrafoundry.providers._netapp.ontap\n"
        "import infrafoundry.core.runners.ontap_rest_runner\n"
        "assert not [m for m in sys.modules if m.startswith('pynetappfoundry')], 'imported'\n"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr


def _target(env: str | None = "test") -> CertificateTarget:
    return CertificateTarget(
        provider="ontap", resource="cluster", key_path="", kind="cluster", env=env
    )


def test_install_certificate_delegates_to_the_installer(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    settings = object()
    with (
        patch("infrafoundry.providers.ontap.load_settings", return_value=settings) as load,
        patch("infrafoundry.providers.ontap.OntapCertificateInstaller") as installer,
    ):
        provider.install_certificate(_target(), "leaf", "chain", "key")

    load.assert_called_once_with(tmp_path, "test")
    installer.assert_called_once_with(settings)
    installer.return_value.install.assert_called_once_with(_target(), "leaf", "chain", "key")


def test_the_install_needs_an_environment(tmp_path: Path) -> None:
    with pytest.raises(CertificateInstallError, match="environment"):
        _provider(tmp_path).install_certificate(_target(None), "leaf", "chain", "key")


def test_unusable_settings_fail_the_install_without_secrets(tmp_path: Path) -> None:
    error = OntapSettingsError("provider_settings.ontap is missing: password")
    with (
        patch("infrafoundry.providers.ontap.load_settings", side_effect=error),
        pytest.raises(CertificateInstallError, match="missing: password"),
    ):
        _provider(tmp_path).install_certificate(_target(), "leaf", "chain", "key")
