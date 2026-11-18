"""Tests for the MikroTik provider."""

from pathlib import Path

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
