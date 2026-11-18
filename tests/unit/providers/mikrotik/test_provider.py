"""Tests for the MikroTik provider."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from infrafoundry.core.protocols import ValidatesOffline
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.mikrotik import MikroTikProvider
from infrafoundry.providers.mikrotik.schema import SPECS

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
        "ip.service",
    ]


def test_dependencies_cover_every_type(tmp_path: Path) -> None:
    deps = _provider(tmp_path).get_dependencies()
    assert set(deps) == set(SPECS)
    assert deps["interface.bridge.port"] == ["interface.bridge"]


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
