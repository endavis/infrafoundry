"""OPNsenseDirectRunner with several firewalls: instance providers and labels (#1450)."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.runners.opnsense_direct_runner import OPNsenseDirectRunner
from infrafoundry.providers.opnsense.services.vlan import Diff


def _provider(tmp_path: Path, name: str, label: Any = None) -> MagicMock:
    provider = MagicMock()
    provider.name = name
    provider._current_environment = "prod"
    provider.config_dir = tmp_path
    provider.firewall_label.return_value = label
    provider.post_apply_hook.return_value = "HA sync done"
    provider.check_endpoint_support.return_value = {"errors": [], "warnings": ["old box"]}
    return provider


def _vlan(provider: str) -> ResourceConfig:
    return ResourceConfig(
        name="lan",
        type="interfaces.vlans",
        provider=provider,
        config={"device": "igb0", "tag": 10, "description": "", "priority": 0},
    )


def _manager() -> tuple[MagicMock, MagicMock]:
    manager = MagicMock()
    manager.plan.return_value = Diff()
    manager.apply.return_value = {
        "success": True,
        "resources_created": 1,
        "resources_updated": 0,
        "resources_deleted": 0,
        "warnings": ["careful"],
    }
    manager.destroy.return_value = {"resources_destroyed": 1}
    manager.get_resource_ids.return_value = {"lan": "uuid-1"}
    return MagicMock(return_value=manager), manager


def _runner() -> tuple[OPNsenseDirectRunner, StringIO]:
    buffer = StringIO()
    return OPNsenseDirectRunner(Console(file=buffer, width=200, force_terminal=False)), buffer


@pytest.mark.parametrize(
    ("name", "supported"),
    [("opnsense", True), ("opnsense@fw-b", True), ("proxmox", False), ("proxmox@x", False)],
)
def test_supports_direct_api_for_instances(name: str, supported: bool) -> None:
    provider = MagicMock()
    provider.name = name
    assert OPNsenseDirectRunner._supports_direct_api(provider) is supported


class TestProviderNameKwarg:
    def _run_all(self, tmp_path: Path, name: str) -> MagicMock:
        provider = _provider(tmp_path, name)
        manager_cls, manager = _manager()
        provider.get_direct_api_resource_types.return_value = {"interfaces.vlans": manager_cls}
        runner, _ = _runner()
        with patch.object(
            OPNsenseDirectRunner, "_load_provider_resources", return_value=[_vlan(name)]
        ):
            runner.plan(provider)
            runner.apply(provider)
            runner.destroy(provider)
            runner.get_resource_ids(provider)
        return manager

    def test_instance_passes_its_name_to_every_manager_call(self, tmp_path: Path) -> None:
        manager = self._run_all(tmp_path, "opnsense@fw-b")
        for method in (manager.plan, manager.apply, manager.destroy, manager.get_resource_ids):
            assert method.call_args.kwargs["provider_name"] == "opnsense@fw-b"

    def test_primary_passes_no_provider_name(self, tmp_path: Path) -> None:
        manager = self._run_all(tmp_path, "opnsense")
        for method in (manager.plan, manager.apply, manager.destroy, manager.get_resource_ids):
            assert "provider_name" not in method.call_args.kwargs


class TestLabels:
    def _output(self, tmp_path: Path, label: Any) -> str:
        provider = _provider(tmp_path, "opnsense@fw-b", label)
        manager_cls, _ = _manager()
        provider.get_direct_api_resource_types.return_value = {"interfaces.vlans": manager_cls}
        runner, buffer = _runner()
        with patch.object(
            OPNsenseDirectRunner, "_load_provider_resources", return_value=[_vlan("opnsense@fw-b")]
        ):
            runner.plan(provider)
            runner.apply(provider)
            runner.destroy(provider)
        return buffer.getvalue()

    def test_label_names_the_firewall_on_every_line(self, tmp_path: Path) -> None:
        output = self._output(tmp_path, "fw-b")
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        assert lines
        assert all(line.startswith("opnsense_direct[fw-b]:") for line in lines)
        assert any("old box" in line for line in lines)
        assert any("careful" in line for line in lines)
        assert any("HA sync done" in line for line in lines)

    @pytest.mark.parametrize("label", [None, MagicMock(), 3, ""])
    def test_without_a_string_label_output_is_the_legacy_one(
        self, tmp_path: Path, label: Any
    ) -> None:
        output = self._output(tmp_path, label)
        assert "opnsense_direct[" not in output
        assert "opnsense_direct:" in output

    def test_label_survives_rich_markup(self, tmp_path: Path) -> None:
        provider = _provider(tmp_path, "opnsense@fw-b", "fw-b")
        runner, buffer = _runner()
        runner.console.print(f"{runner._label(provider)}: line")
        assert buffer.getvalue().strip() == "opnsense_direct[fw-b]: line"

    def test_plain_mock_provider_gets_the_legacy_label(self, tmp_path: Path) -> None:
        provider = MagicMock()
        provider.name = "opnsense"
        provider._current_environment = "prod"
        assert OPNsenseDirectRunner()._label(provider) == "opnsense_direct"


class TestPostApplyHookPerFirewall:
    def test_hook_fires_once_per_provider_instance(self, tmp_path: Path) -> None:
        runner, _ = _runner()
        providers = [_provider(tmp_path, "opnsense"), _provider(tmp_path, "opnsense@fw-b")]
        for provider in providers:
            manager_cls, _ = _manager()
            provider.get_direct_api_resource_types.return_value = {"interfaces.vlans": manager_cls}
            with patch.object(
                OPNsenseDirectRunner,
                "_load_provider_resources",
                return_value=[_vlan(provider.name)],
            ):
                runner.apply(provider)
        for provider in providers:
            provider.post_apply_hook.assert_called_once_with("prod", True)


def test_resources_are_filtered_per_firewall() -> None:
    config_manager = MagicMock()
    config_manager.get_all_resources_all_providers.return_value = [
        _vlan("opnsense"),
        _vlan("opnsense@fw-b"),
    ]
    provider = MagicMock()
    provider.name = "opnsense@fw-b"
    provider._current_environment = "prod"
    provider.config_dir = Path("cfg")
    with patch("infrafoundry.core.config.ConfigManager", return_value=config_manager):
        resources = OPNsenseDirectRunner()._load_provider_resources(provider)
    assert [r.provider for r in resources] == ["opnsense@fw-b"]
