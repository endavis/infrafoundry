"""Tests for PackageLoader resource parsing."""

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.provider import ResourceConfig


@pytest.fixture
def loader(tmp_path: Path) -> PackageLoader:
    """Create a PackageLoader with a temporary base directory."""
    return PackageLoader(tmp_path)


class TestParseResourceCentric:
    """Tests for _parse_resource_centric parsing logic."""

    def _parse(
        self,
        loader: PackageLoader,
        resources: list[dict[str, Any]],
        resource_file: str = "resources.yaml",
        default_provider: str = "proxmox",
    ) -> list[ResourceConfig]:
        """Helper to call _parse_resource_centric."""
        return loader._parse_resource_centric(resources, resource_file, default_provider)

    def test_explicit_config_key_injects_name(self, loader: PackageLoader) -> None:
        """When a resource has an explicit config key, name is injected into config."""
        resources = [
            {
                "provider": "proxmox",
                "type": "storage",
                "name": "infra",
                "config": {
                    "backend": "nfs",
                    "server": "192.168.10.50",
                },
            }
        ]
        result = self._parse(loader, resources)
        assert len(result) == 1
        assert result[0].name == "infra"
        assert result[0].config["name"] == "infra"
        assert result[0].config["backend"] == "nfs"

    def test_explicit_config_key_does_not_override_existing_name(
        self, loader: PackageLoader
    ) -> None:
        """If config already contains name, it is not overridden."""
        resources = [
            {
                "provider": "proxmox",
                "type": "storage",
                "name": "infra",
                "config": {
                    "name": "custom-name",
                    "backend": "nfs",
                },
            }
        ]
        result = self._parse(loader, resources)
        assert result[0].config["name"] == "custom-name"

    def test_no_config_key_uses_full_item(self, loader: PackageLoader) -> None:
        """Without explicit config key, the full item dict is used as config."""
        resources = [
            {
                "provider": "proxmox",
                "type": "vm",
                "name": "test-vm",
                "cores": 4,
                "memory": 8192,
            }
        ]
        result = self._parse(loader, resources)
        assert len(result) == 1
        assert result[0].config["name"] == "test-vm"
        assert result[0].config["cores"] == 4
        assert result[0].config["memory"] == 8192

    def test_default_provider_used_when_not_specified(self, loader: PackageLoader) -> None:
        """Resources without provider field use the default provider."""
        resources = [
            {
                "type": "vm",
                "name": "test-vm",
            }
        ]
        result = self._parse(loader, resources, default_provider="esxi")
        assert result[0].provider == "esxi"

    def test_explicit_provider_overrides_default(self, loader: PackageLoader) -> None:
        """Resources with provider field override the default."""
        resources = [
            {
                "provider": "kubernetes",
                "type": "namespace",
                "name": "test-ns",
            }
        ]
        result = self._parse(loader, resources, default_provider="proxmox")
        assert result[0].provider == "kubernetes"

    def test_missing_type_raises_error(self, loader: PackageLoader) -> None:
        """Resources without type field raise InvalidConfigurationError."""
        from infrafoundry.core.exceptions import InvalidConfigurationError

        resources = [{"name": "test"}]
        with pytest.raises(InvalidConfigurationError, match="missing 'type'"):
            self._parse(loader, resources)

    def test_items_without_name_are_skipped(self, loader: PackageLoader) -> None:
        """Items without a name field are silently skipped."""
        resources = [
            {"type": "vm"},  # no name
            {"type": "vm", "name": "valid"},
        ]
        result = self._parse(loader, resources)
        assert len(result) == 1
        assert result[0].name == "valid"

    def test_non_dict_items_are_skipped(self, loader: PackageLoader) -> None:
        """Non-dict items in the resources list are skipped."""
        resources = ["not-a-dict", {"type": "vm", "name": "valid"}]  # type: ignore[list-item]
        result = self._parse(loader, resources)
        assert len(result) == 1


class TestParseResourcesFromData:
    """Tests for _parse_resources_from_data covering both formats."""

    def test_resource_centric_format(self, loader: PackageLoader) -> None:
        """Data with 'resources' key uses resource-centric parsing."""
        data = {
            "resources": [
                {
                    "provider": "proxmox",
                    "type": "storage",
                    "name": "infra",
                    "config": {"backend": "nfs"},
                }
            ]
        }
        result = loader._parse_resources_from_data(data, "resources.yaml", "proxmox")
        assert len(result) == 1
        assert result[0].config["name"] == "infra"

    def test_provider_centric_format(self, loader: PackageLoader) -> None:
        """Data with type-named key uses provider-centric parsing."""
        data = {
            "vm": [
                {"name": "test-vm", "cores": 4},
            ]
        }
        result = loader._parse_resources_from_data(data, "vm.yaml", "proxmox")
        assert len(result) == 1
        assert result[0].type == "vm"
        assert result[0].config["name"] == "test-vm"

    def test_empty_data_returns_empty(self, loader: PackageLoader) -> None:
        """Empty data returns empty list."""
        result = loader._parse_resources_from_data({}, "vm.yaml", "proxmox")
        assert result == []
