"""Tests for the MikroTik provider."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.certs.install import CertificateTarget
from infrafoundry.core.certs.models import CertificateInstallError
from infrafoundry.core.protocols import InstallsCertificate, ValidatesOffline
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.mikrotik import MikroTikProvider
from infrafoundry.providers.mikrotik.components.update import UPDATE_TYPE
from infrafoundry.providers.mikrotik.schema import SPECS
from infrafoundry.providers.mikrotik.settings import MikroTikSettings, MikroTikSettingsError

from .conftest import make_env, resource


def _provider(tmp_path: Path) -> MikroTikProvider:
    provider = MikroTikProvider(tmp_path, tmp_path / "generated")
    provider.set_environment("test")
    return provider


def test_resource_types(tmp_path: Path) -> None:
    assert _provider(tmp_path).get_resource_types() == [
        "interface.bridge",
        "interface.bridge.port",
        "interface.bridge.vlan",
        "interface.vlan",
        "ip.address",
        "ip.dhcp-client",
        "certificate",
        "ip.service",
        "system.package.update",
    ]


def test_dependencies_cover_every_type(tmp_path: Path) -> None:
    deps = _provider(tmp_path).get_dependencies()
    assert set(deps) == {*SPECS, UPDATE_TYPE}
    assert deps["interface.bridge.port"] == ["interface.bridge"]
    assert deps["certificate"] == []


def test_terraform_prefixes_match_runner_outcome_addresses(tmp_path: Path) -> None:
    prefixes = _provider(tmp_path).get_terraform_resource_types()
    assert prefixes["interface.bridge.port"] == ["mikrotik_interface_bridge_port"]
    assert prefixes["ip.dhcp-client"] == ["mikrotik_ip_dhcp_client"]


def test_generate_terraform_writes_empty_block(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    provider.generate_terraform([resource("interface.bridge", "bridge")])
    text = (provider.terraform_dir / "main.tf").read_text()
    assert "terraform {}" in text


def test_dispatch_hook_and_ansible(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    provider.generate_mikrotik_rest([])
    provider.generate_ansible([])
    assert provider.ansible_dir.is_dir()


def test_implements_validates_offline(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    assert isinstance(provider, ValidatesOffline)
    report = ValidationReport()
    provider.validate_offline(
        [resource("interface.bridge", "b", bogus=1)], [], make_env({}), report
    )
    assert any(not r.passed for r in report.results)


def test_deletable_types_exclude_services(tmp_path: Path) -> None:
    deletable = _provider(tmp_path).deletable_types()
    assert "interface.bridge" in deletable and "ip.service" not in deletable


def test_rest_apply_plans_then_applies_on_one_manager(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    resources = [resource("interface.bridge", "bridge")]
    with patch("infrafoundry.providers.mikrotik.MikroTikManager") as cls:
        manager: MagicMock = cls.return_value
        result = provider.rest_apply("test", resources, add_only=True, target_resources=["bridge"])

    cls.assert_called_once_with(tmp_path)
    manager.plan.assert_called_once_with(
        "test", resources, add_only=True, managed_resources=None, target_resources=["bridge"]
    )
    manager.apply.assert_called_once_with("test", manager.plan.return_value)
    assert result is manager.apply.return_value


def test_rest_destroy_and_resource_ids_delegate(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    resources = [resource("interface.bridge", "bridge")]
    with patch("infrafoundry.providers.mikrotik.MikroTikManager") as cls:
        manager: MagicMock = cls.return_value
        assert provider.rest_destroy("test", resources, target_resources=["a"]) is (
            manager.destroy.return_value
        )
        assert provider.rest_resource_ids("test", resources) is manager.resource_ids.return_value

    manager.destroy.assert_called_once_with("test", resources, target_resources=["a"])
    manager.resource_ids.assert_called_once_with("test", resources)


def test_terraform_prefix_for_update_type(tmp_path: Path) -> None:
    prefixes = _provider(tmp_path).get_terraform_resource_types()
    assert prefixes[UPDATE_TYPE] == ["mikrotik_system_package_update"]


def test_update_plan_lines(tmp_path: Path) -> None:
    from infrafoundry.core.exceptions import InfraFoundryError
    from infrafoundry.providers.mikrotik.settings import MikroTikSettingsError

    from .conftest import SETTINGS
    from .update_fake import FakeUpdateDevice

    provider = _provider(tmp_path)
    update = resource(UPDATE_TYPE, "ros")
    assert provider.update_plan_lines("test", [resource("ip.service", "x")]) == []
    with (
        patch("infrafoundry.providers.mikrotik.load_settings", return_value=SETTINGS),
        patch("infrafoundry.providers.mikrotik.RouterOSClient", return_value=FakeUpdateDevice()),
    ):
        [(line, warning)] = provider.update_plan_lines("test", [update])
    assert "7.24 → 7.25 available" in line and not warning
    with patch(
        "infrafoundry.providers.mikrotik.load_settings", side_effect=MikroTikSettingsError("no")
    ):
        [(line, warning)] = provider.update_plan_lines("test", [update])
    assert warning and "update check failed" in line
    with (
        patch("infrafoundry.providers.mikrotik.load_settings", return_value=SETTINGS),
        patch("infrafoundry.providers.mikrotik.check_update", side_effect=InfraFoundryError("x")),
    ):
        assert provider.update_plan_lines("test", [update])[0][1]


def test_register_exposes_cli_hook() -> None:
    from infrafoundry.providers.mikrotik import register, register_cli

    metadata = register()
    assert metadata.name == "mikrotik" and metadata.cli_registration is register_cli
    assert UPDATE_TYPE in metadata.resource_types


def _target(env: str | None = "test") -> Any:
    return CertificateTarget(
        provider="mikrotik",
        resource="edge-services",
        key_path="",
        verify_server_name="router.example.com",
        env=env,
    )


def test_the_provider_installs_certificates(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    assert isinstance(provider, InstallsCertificate)
    settings = MikroTikSettings("https://192.0.2.2", "admin", "pw-example")
    with (
        patch("infrafoundry.providers.mikrotik.load_settings", return_value=settings) as load,
        patch("infrafoundry.providers.mikrotik.RouterOSCertificateInstaller") as installer,
    ):
        provider.install_certificate(_target(), "leaf", "chain", "key")

    load.assert_called_once_with(tmp_path, "test")
    installer.assert_called_once_with(settings)
    installer.return_value.install.assert_called_once_with(_target(), "leaf", "chain", "key")


def test_the_install_needs_an_environment(tmp_path: Path) -> None:
    with pytest.raises(CertificateInstallError, match="environment"):
        _provider(tmp_path).install_certificate(_target(None), "leaf", "chain", "key")


def test_unusable_settings_fail_the_install_without_secrets(tmp_path: Path) -> None:
    error = MikroTikSettingsError("provider_settings.mikrotik is missing: password")
    with (
        patch("infrafoundry.providers.mikrotik.load_settings", side_effect=error),
        pytest.raises(CertificateInstallError, match="missing: password"),
    ):
        _provider(tmp_path).install_certificate(_target(), "leaf", "chain", "key")
